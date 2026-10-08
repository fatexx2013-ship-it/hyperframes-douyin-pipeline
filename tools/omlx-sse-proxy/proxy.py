#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
oMLX / vMLX SSE 清洗代理

修复问题：
  vMLX 引擎流式返回工具调用时，第一个 tool_calls 分片的 function.name 是空字符串，
  OpenCode 的 AI SDK 会立刻把它当成"名为空字符串的工具调用"并整包拒绝
  （报错 Model tried to call unavailable tool ''），随后的正确分片也不会再被采纳。

做法：
  对 text/event-stream 响应，缓冲"只有空 name 的工具调用起始分片"，
  等后续分片带出真实工具名后，把名字改写进起始分片、删掉后续分片里的
  重复 name，输出标准 OpenAI 流式形态（首片 id+name，之后只有 arguments）；
  普通文本、reasoning_content 与非流式请求原样透传。

用法：
  python3 proxy.py                 # 监听 127.0.0.1:8001 -> 转发 127.0.0.1:8000
  UPSTREAM=127.0.0.1:8081 PORT=8002 python3 proxy.py
"""
import json
import os
import re
import sys
import uuid
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM_HOST, UPSTREAM_PORT = (os.environ.get("UPSTREAM", "127.0.0.1:8000").split(":", 1) + ["8000"])[:2]
UPSTREAM_PORT = int(UPSTREAM_PORT)
LISTEN_PORT = int(os.environ.get("PORT", "8001"))
DUMP_DIR = os.environ.get("DUMP_DIR", "")
_dump_seq = 0

HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
              "te", "trailers", "transfer-encoding", "upgrade", "content-length", "host"}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[proxy] %s - %s\n" % (self.address_string(), fmt % args))

    def _forward(self):
        global _dump_seq
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""
        # 解析请求里的工具清单，供内容层"信封重建"时做路由
        valid_names: set[str] = set()
        try:
            reqj = json.loads(body.decode("utf-8", "replace"))
            for t in reqj.get("tools") or []:
                nm = (t.get("function") or {}).get("name")
                if nm:
                    valid_names.add(nm)
        except Exception:
            pass

        dump_fh = None
        if DUMP_DIR and self.path.endswith("/chat/completions"):
            try:
                os.makedirs(DUMP_DIR, exist_ok=True)
                _dump_seq += 1
                seq = _dump_seq
                with open(os.path.join(DUMP_DIR, f"req_{seq:03d}.json"), "wb") as f:
                    f.write(body)
                dump_fh = open(os.path.join(DUMP_DIR, f"raw_{seq:03d}.sse.log"), "wb")
            except Exception:
                dump_fh = None
        fwd_headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}
        fwd_headers["Host"] = f"{UPSTREAM_HOST}:{UPSTREAM_PORT}"
        try:
            conn = http.client.HTTPConnection(UPSTREAM_HOST, UPSTREAM_PORT, timeout=600)
            conn.request(self.command, self.path, body=body, headers=fwd_headers)
            resp = conn.getresponse()
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            msg = f"proxy upstream error: {e}".encode()
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
            return

        ctype = resp.getheader("Content-Type", "")
        is_sse = "text/event-stream" in ctype

        if not is_sse:
            # 非 SSE（含 /v1/models、非流式补全）：读完整个 body 后自带
            # Content-Length 回传并主动关连接，避免上游 chunked 导致客户端挂死。
            data = resp.read()
            conn.close()
            self.send_response(resp.status, resp.reason)
            for k, v in resp.getheaders():
                if k.lower() in HOP_BY_HOP:
                    continue
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.close_connection = True
            self.end_headers()
            if data:
                self.wfile.write(data)
            self.wfile.flush()
            return

        # SSE：长度未知，用 chunked 透传（下方做工具调用分片清洗）
        self.send_response(resp.status, resp.reason)
        for k, v in resp.getheaders():
            if k.lower() in HOP_BY_HOP:
                continue
            self.send_header(k, v)
        self.send_header("Transfer-Encoding", "chunked")
        self.close_connection = True
        self.end_headers()

        # ---- SSE 清洗（两层）----
        # 第 1 层 · 结构化 tool_calls 分片：
        #   vMLX 先发 {"name":"","arguments":""} 起始片，再发带真实名字的第二片，
        #   AI SDK 见到空 name 立即判非法。规范化为标准形态：名字只在首片。
        # 第 2 层 · content 里的 Harmony 泄漏：
        #   解析器偶发失手，把 `to=tool.bash<|constrain|>json<|message|>{...}`
        #   整段（或残缺的 `to=skill call name=`、裸 `<|message|>` 标记）当正文
        #   吐给客户端。这里剥掉控制标记，把完整信封重建成结构化 tool_calls，
        #   残缺残尾直接丢弃（引擎在同一轮通常已另外发出了结构化调用）。
        resolved = {}         # (choice, index) -> 已知非空 name
        name_emitted = set()  # 已写过 name 的 key
        pending = set()       # 出现但还没拿到非空 name 的 key
        held = []             # 涉及未决 key、暂未放行的原始行
        max_tc_index = -1     # 结构化分片里出现过的最大 tool 索引
        synth_count = 0       # 本轮由代理重建的工具调用数
        ctail = {}            # choice -> 暂挂的 content 文本（跨分片拼信封）
        ev_tpl = {}           # 合成事件用的 id/model/created 模板

        ENV_HEAD = re.compile(
            r"to=\s*(?:functions\.|tool\.)?([A-Za-z_][\w.\-]*)[^\n{]{0,80}?(\{)", re.DOTALL
        )
        TOOLCALL_TAG = re.compile(r"<tool_call>\s*(\{)", re.DOTALL)
        CTRL_TOKEN = re.compile(r"<\|[^|<>]{1,40}\|>")
        FORMING = re.compile(r"to=\s*(?:functions\.|tool\.)?[A-Za-z_][\w.\-]*[^\n{]{0,80}$")
        RESIDUE_TAIL = re.compile(
            r"\n?to=\s*(?:functions\.|tool\.)?[A-Za-z_][\w.\-]*[^\n]{0,200}$"
        )

        def load_data(raw: bytes):
            line = raw.strip()
            if not line.startswith(b"data:"):
                return None
            payload = line[5:].strip()
            if payload == b"[DONE]":
                return False
            try:
                return json.loads(payload.decode("utf-8", "replace"))
            except Exception:
                return None

        def scan_json_object(s: str, start: int, max_len: int = 20000):
            """从 '{' 起做括号配平，返回结束位置（exclusive）；未闭合返回 None。"""
            if start >= len(s) or s[start] != "{":
                return None
            depth = 0
            in_str = esc = False
            stop = min(len(s), start + max_len)
            for i in range(start, stop):
                c = s[i]
                if in_str:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                    continue
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        return i + 1
            return None

        def tool_keys(ev):
            out = []
            for ci, ch in enumerate(ev.get("choices") or []):
                for tc in (ch or {}).get("delta", {}).get("tool_calls") or []:
                    nm = (tc.get("function") or {}).get("name") or None
                    out.append((ci, tc.get("index", 0), nm))
            return out

        def write_raw(raw: bytes):
            self.wfile.write(b"%x\r\n%b\r\n" % (len(raw), raw))

        def emit_json(ev: dict):
            # SSE 事件必须以空行（\n\n）结束；少一个 \n 会让客户端把连续多个
            # data: 行拼成一个数据包，导致 JSON.parse 直接失败。
            out = b"data: " + json.dumps(ev, ensure_ascii=False).encode() + b"\n\n"
            write_raw(out)

        def rewrite_names(ev):
            """结构化分片就地规范化：首片补真实 name，其后删掉 name。"""
            for ch in ev.get("choices") or []:
                for tc in (ch or {}).get("delta", {}).get("tool_calls") or []:
                    fn = tc.get("function")
                    if fn is None:
                        continue
                    key = (ev.get("choices", []).index(ch), tc.get("index", 0))
                    if key in name_emitted:
                        fn.pop("name", None)
                    elif resolved.get(key):
                        fn["name"] = resolved[key]
                        name_emitted.add(key)

        def write_event(raw: bytes):
            ev = load_data(raw)
            if isinstance(ev, dict):
                rewrite_names(ev)
                emit_json(ev)
            else:
                write_raw(raw)

        def flush_held():
            if not held:
                return
            batch, held[:] = held[:], []
            for h in batch:
                write_event(h)
            self.wfile.flush()

        def synth_call(name: str, args_text: str):
            """把 content 里抢救出来的一个调用按标准两片发出去。"""
            nonlocal max_tc_index, synth_count
            idx = max_tc_index + 1
            max_tc_index = idx
            synth_count += 1
            base = {
                "id": ev_tpl.get("id", "chatcmpl-proxy"),
                "object": "chat.completion.chunk",
                "created": ev_tpl.get("created", 0),
                "model": ev_tpl.get("model", ""),
            }
            emit_json({**base, "choices": [{"index": 0, "delta": {
                "role": "assistant",
                "tool_calls": [{
                    "index": idx,
                    "id": f"call_proxy_{uuid.uuid4().hex[:12]}",
                    "type": "function",
                    "function": {"name": name, "arguments": ""},
                }]}, "finish_reason": None}], "usage": None})
            emit_json({**base, "choices": [{"index": 0, "delta": {
                "tool_calls": [{"index": idx, "function": {"arguments": args_text}}]
            }, "finish_reason": None}], "usage": None})

        def route_call(name: str, args_text: str):
            """按请求工具清单路由；未知接收者模仿插件修复成 skill 调用。"""
            if valid_names and name in valid_names:
                synth_call(name, args_text)
                return
            if (
                valid_names
                and "skill" in valid_names
                and "." not in name
                and re.fullmatch(r"[A-Za-z][A-Za-z0-9_\-]{0,63}", name)
            ):
                synth_call("skill", json.dumps({"name": name}, ensure_ascii=False))
                return
            # 无法路由：静默丢弃，绝不把协议残文当回答放出去

        def extract_envelopes(text: str):
            """从文本中摘出全部完整 harmony / <tool_call> 信封。

            返回 (剩余文本, [(name, args_text), ...], unclosed_at)。
            """
            calls = []
            unclosed_at = None
            while True:
                m = ENV_HEAD.search(text)
                if m:
                    head_start, brace = m.start(), m.start(2)
                    end = scan_json_object(text, brace)
                    if end is None:
                        unclosed_at = head_start
                        break
                    raw_args = text[brace:end]
                    text = text[:head_start] + text[end:]
                    try:
                        payload = json.loads(raw_args)
                    except Exception:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    name = m.group(1).strip()
                    if isinstance(payload.get("name"), str) and payload["name"].strip():
                        # `to=<recipient> {tool-call envelope}` 混合写法：信封为准
                        name = payload["name"].strip()
                        inner = payload.get("arguments", payload.get("parameters"))
                        args_text = (
                            json.dumps(inner, ensure_ascii=False)
                            if isinstance(inner, dict) else "{}"
                        )
                    else:
                        args_text = json.dumps(payload, ensure_ascii=False)
                    if name:
                        calls.append((name, args_text))
                    continue

                tm = TOOLCALL_TAG.search(text)
                if tm:
                    brace = tm.end() - 1
                    end = scan_json_object(text, brace)
                    if end is None:
                        unclosed_at = tm.start()
                        break
                    raw_args = text[brace:end]
                    close = text.find("</tool_call>", end)
                    seg_end = close + len("</tool_call>") if close >= 0 else end
                    text = text[:tm.start()] + text[seg_end:]
                    try:
                        payload = json.loads(raw_args)
                    except Exception:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    name = str(payload.get("name") or "").strip()
                    args = payload.get("arguments", payload.get("parameters", {}))
                    args_text = (
                        json.dumps(args, ensure_ascii=False) if isinstance(args, dict)
                        else json.dumps({"value": args}, ensure_ascii=False)
                    )
                    if name:
                        calls.append((name, args_text))
                    continue
                break
            return text, calls, unclosed_at

        def process_content(ev: dict):
            """处理一个 data 事件里所有 choice 的 content；就地改写/发出合成调用。"""
            for ci, ch in enumerate(ev.get("choices") or []):
                delta = (ch or {}).get("delta") or {}
                text = delta.get("content")
                if not isinstance(text, str):
                    continue
                ev_tpl.update({k: ev.get(k) for k in ("id", "created", "model")})
                # 注意：挂起区间必须在"带控制标记的原文"上判定。若先剥 <|...|>，
                # `to=tool.bash` + `<|constrain|>json` 会粘连成 `bashjson`，
                # 导致下一轮把接收者识别错。
                t = ctail.get(ci, "") + text
                t, calls, unclosed_at = extract_envelopes(t)
                for nm, args_text in calls:
                    route_call(nm, args_text)
                hold_start = None
                if unclosed_at is not None:
                    hold_start = unclosed_at
                else:
                    fm = FORMING.search(t)
                    if fm:
                        hold_start = fm.start()
                    else:
                        lt, gt = t.rfind("<|"), t.rfind("|>")
                        if lt > gt and lt >= len(t) - 44:
                            hold_start = lt
                if hold_start is not None:
                    ctail[ci] = t[hold_start:]   # 原文挂起，不剥标记
                    t = t[:hold_start]
                else:
                    ctail[ci] = ""
                # 只对确定要放行的前缀摘控制标记
                delta["content"] = CTRL_TOKEN.sub("", t)

        def flush_ctail(final: bool):
            """轮次结束/[DONE] 时放掉挂起的 content；残缺调用残尾直接丢弃。"""
            for ci, buf in list(ctail.items()):
                if not buf:
                    continue
                t = CTRL_TOKEN.sub("", buf)
                if final:
                    t2 = RESIDUE_TAIL.sub("", t).strip()
                    t = t2
                ctail[ci] = ""
                if t:
                    emit_json({
                        "id": ev_tpl.get("id", "chatcmpl-proxy"),
                        "object": "chat.completion.chunk",
                        "created": ev_tpl.get("created", 0),
                        "model": ev_tpl.get("model", ""),
                        "choices": [{"index": ci, "delta": {"content": t}}],
                        "usage": None,
                    })
            self.wfile.flush()

        for raw in resp:
            if dump_fh is not None:
                dump_fh.write(raw)
                dump_fh.flush()
            ev = load_data(raw)
            if ev is False:  # data: [DONE]
                flush_held()
                flush_ctail(final=True)
                write_raw(raw)
                self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
                conn.close()
                if dump_fh is not None:
                    dump_fh.close()
                return

            if not isinstance(ev, dict):
                write_raw(raw)
                self.wfile.flush()
                continue

            ev_tpl.update({k: ev.get(k) for k in ("id", "created", "model")})
            keys = tool_keys(ev)
            if keys:
                for ci, idx, nm in keys:
                    max_tc_index = max(max_tc_index, idx)
                    key = (ci, idx)
                    if nm:
                        resolved[key] = nm
                    if key not in pending and key not in resolved:
                        pending.add(key)
                    elif key in pending and nm:
                        pass
                if pending and not all(k in resolved for k in list(pending)):
                    held.append(raw)
                    if all(k in resolved for k in pending):
                        flush_held()
                else:
                    if held:
                        held.append(raw)
                        flush_held()
                    else:
                        rewrite_names(ev)
                        emit_json(ev)
                        self.wfile.flush()
                continue

            # finish 事件：若本轮代理重建过调用，stop 必须改成 tool_calls
            for ch in ev.get("choices") or []:
                fr = (ch or {}).get("finish_reason")
                if fr == "stop" and synth_count > 0:
                    ch["finish_reason"] = "tool_calls"

            has_content = any(
                isinstance((c or {}).get("delta", {}).get("content"), str)
                for c in ev.get("choices") or []
            )
            if has_content and not held:
                process_content(ev)
                # 仅当至少一个 choice 还剩可见内容（或非 content 字段）时才发出
                alive = False
                for c in ev.get("choices") or []:
                    d = (c or {}).get("delta") or {}
                    d.pop("content", None) if d.get("content") == "" else None
                    if d or c.get("finish_reason"):
                        alive = True
                if alive:
                    emit_json(ev)
                self.wfile.flush()
            elif held:
                held.append(raw)
            else:
                emit_json(ev)
                self.wfile.flush()

        flush_held()
        flush_ctail(final=True)
        self.wfile.write(b"0\r\n\r\n")
        conn.close()
        if dump_fh is not None:
            dump_fh.close()

    do_GET = _forward
    do_POST = _forward
    do_OPTIONS = _forward


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", LISTEN_PORT), Handler)
    print(f"oMLX SSE 清洗代理: http://127.0.0.1:{LISTEN_PORT} -> http://{UPSTREAM_HOST}:{UPSTREAM_PORT}", flush=True)
    srv.serve_forever()
