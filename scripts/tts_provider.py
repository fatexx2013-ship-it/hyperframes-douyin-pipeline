#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tts_provider.py —— 可插拔 TTS provider 抽象层

两个 provider
-------------
1) ``mlx``（默认档，行为与改造前逐字节一致）
   本地 MLX Qwen3-TTS（Apple Silicon 专属）。旁白走
   ``generate_qa_video.generate_qwen3_tts(text, out, role)``；
   片尾走 ``generate_news_card_video.batch_tts([(text, out)], work, emotion)``。
   调用签名、参数顺序、输出规格（24000Hz/mono）与既有链路完全一致。

2) ``openai``（新增，跨平台可用）
   OpenAI 兼容云端 TTS：``POST {base_url}/audio/speech``。
   凭据只读环境变量（``TTS_API_KEY``），不落盘、不回显、不写日志。

硬约束
------
- **未配置即明确报错，绝不静默降级**：指定了 `openai` 却缺 base_url/api_key，
  或指定了 `mlx` 却不在 Apple Silicon，一律抛 ``TtsConfigError`` 并给出可照抄的修复命令。
- 不改变任何产线参数（24000Hz / mono 出口口径不变）。

用法
----
    import tts_provider

    # 旁白（逐句）
    tts_provider.synthesize("今天拆一个项目", "line_00.raw.wav", role="answer")

    # 片尾口播（带情绪音色）
    tts_provider.synthesize("关注 jerrychen2001", "epilogue.raw.wav",
                            emotion="thoughtful", work_dir="/tmp/work")

    # 只做配置自检（不联网、不加载模型）
    ok, why = tts_provider.probe()
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(_HERE)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import platform_env  # noqa: E402

CONFIG_PATH = os.path.join(REPO_ROOT, "config", "tts.json")
PROVIDER_ENV = "TTS_PROVIDER"
VALID_PROVIDERS = ("mlx", "openai")
DOC_HINT = "详见 docs/DEPLOY.md「TTS 配置」章节"


class TtsError(RuntimeError):
    """TTS 链路错误基类。"""


class TtsConfigError(TtsError):
    """配置缺失/不合法：报错必须可直接照抄修复。"""


class TtsRuntimeError(TtsError):
    """合成期错误（模型加载、HTTP 失败等）。"""


# ── 配置加载 ──────────────────────────────────────────────────────────────

def _ctx() -> dict:
    return {
        "REPO_ROOT": REPO_ROOT,
        "PIPELINE_HOME": os.environ.get("PIPELINE_HOME", ""),
        "HOME": os.path.expanduser("~"),
        "QWEN3_TTS_DIR": os.environ.get("QWEN3_TTS_DIR", "~/Projects/qwen3-tts-apple-silicon"),
    }


def _expand(value, ctx=None):
    """展开 ${VAR} / ${VAR:-default} 与 ~。不做凭据持久化，仅读环境变量。"""
    if not isinstance(value, str):
        return value
    ctx = ctx or _ctx()
    out, i = [], 0
    while i < len(value):
        ch = value[i]
        if ch == "$" and i + 1 < len(value) and value[i + 1] == "{":
            end = value.find("}", i + 2)
            if end == -1:
                out.append(value[i:])
                break
            token = value[i + 2:end]
            name, _, default = token.partition(":-")
            name = name.strip()
            val = os.environ.get(name)
            if val is None or val == "":
                val = ctx.get(name, default)
            out.append(str(val if val is not None else ""))
            i = end + 1
        elif ch == "~" and (i == 0 or value[i - 1] in "/\\") and (
                i + 1 == len(value) or value[i + 1] in "/\\"):
            out.append(os.path.expanduser("~"))
            i += 1
        else:
            out.append(ch)
            i += 1
    result = "".join(out)
    if result.startswith("~"):
        result = os.path.expanduser(result)
    return result


def load_config(path=None) -> dict:
    p = path or CONFIG_PATH
    if not os.path.isfile(p):
        raise TtsConfigError(
            f"缺少 TTS 配置真源：{p}\n"
            f"  该文件随仓库提供；若被删除请从 git 恢复：git checkout -- config/tts.json\n"
            f"  {DOC_HINT}"
        )
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def provider_name(cfg=None) -> str:
    """解析生效 provider：环境变量 TTS_PROVIDER > config/tts.json > 默认 mlx。"""
    cfg = cfg or load_config()
    raw = os.environ.get(cfg.get("provider_env") or PROVIDER_ENV, "").strip()
    if not raw:
        raw = str(cfg.get("provider") or "mlx").strip()
    name = raw.lower()
    if name not in VALID_PROVIDERS:
        raise TtsConfigError(
            f"未知 TTS provider：{raw!r}\n"
            f"  可选值：{', '.join(VALID_PROVIDERS)}；设置方式：export {PROVIDER_ENV}=mlx|openai\n"
            f"  {DOC_HINT}"
        )
    return name


# ── provider 实现 ─────────────────────────────────────────────────────────

class _BaseProvider:
    name = ""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.block = (cfg.get("providers") or {}).get(self.name) or {}

    def ready(self):
        """(bool, 说明)：只做本地配置自检，不联网、不加载模型。"""
        raise NotImplementedError

    def synthesize(self, text, out_path, role="answer", emotion=None, work_dir=None) -> dict:
        raise NotImplementedError


class _MlxProvider(_BaseProvider):
    name = "mlx"

    # ── 模块目录解析：环境变量 → config 候选 → 平台默认 ──
    def module_dir(self, module_name):
        ctx = _ctx()
        cands = []
        for c in self.block.get("module_dir_candidates") or []:
            c = _expand(c, ctx)
            if c:
                cands.append(c)
        for c in (os.environ.get("TTS_MLX_MODULE_DIR", ""), os.environ.get("PIPELINE_HOME", "")):
            if c:
                cands.insert(0, c)
        cands.append(os.path.expanduser(self.model_root()))
        seen, ordered = set(), []
        for c in cands:
            if c not in seen:
                seen.add(c)
                ordered.append(c)
        for d in ordered:
            if d and os.path.isfile(os.path.join(d, module_name + ".py")):
                return d
        raise TtsConfigError(
            f"provider=mlx 但找不到 TTS 驱动模块 {module_name}.py。\n"
            f"  已搜索目录：{ordered}\n"
            f"  修复：export TTS_MLX_MODULE_DIR=/含 {module_name}.py 的目录\n"
            f"       （旧产线的默认位置是 /Volumes/PSSD/抖音视频，可直接指向它）\n"
            f"  或改用云端 provider：export {PROVIDER_ENV}=openai（需 TTS_BASE_URL/TTS_API_KEY/TTS_MODEL/TTS_VOICE）\n"
            f"  {DOC_HINT}"
        )

    def model_root(self) -> str:
        key = self.block.get("model_root_env") or "QWEN3_TTS_DIR"
        env_val = os.environ.get(key, "").strip()
        if env_val:
            return env_val
        ctx = _ctx()
        return _expand(self.block.get("model_root") or "~/Projects/qwen3-tts-apple-silicon", ctx)

    def voice_role(self) -> str:
        key = self.block.get("voice_role_env") or "TTS_MLX_VOICE_ROLE"
        return os.environ.get(key, "").strip() or str(self.block.get("voice_role") or "answer")

    def default_emotion(self) -> str:
        key = self.block.get("default_emotion_env") or "TTS_MLX_EMOTION"
        return os.environ.get(key, "").strip() or str(self.block.get("default_emotion") or "thoughtful")

    def ready(self):
        if not platform_env.IS_MACOS:
            return False, (
                f"provider=mlx 仅支持 Apple Silicon（当前平台 {platform_env.platform_name()}）。\n"
                f"  Linux/Windows 请改用云端 provider：export {PROVIDER_ENV}=openai\n"
                f"  （需 TTS_BASE_URL / TTS_API_KEY / TTS_MODEL / TTS_VOICE）\n"
                f"  {DOC_HINT}"
            )
        if not platform_env.is_apple_silicon():
            return False, (
                f"provider=mlx 需要 arm64（Apple Silicon），当前 machine={__import__('platform').machine()}。\n"
                f"  Intel Mac 请改用：export {PROVIDER_ENV}=openai\n  {DOC_HINT}"
            )
        try:
            mod = self.block.get("narration_module") or "generate_qa_video"
            self.module_dir(mod)
        except TtsConfigError as exc:
            return False, str(exc)
        root = os.path.expanduser(self.model_root())
        if not os.path.isdir(root):
            return False, (
                f"provider=mlx 找不到模型根目录：{root}\n"
                f"  修复：export QWEN3_TTS_DIR=/含 models/ 与 voices/ 的目录\n  {DOC_HINT}"
            )
        try:
            import mlx_audio  # noqa: F401
        except Exception:  # noqa: BLE001
            return False, (
                "provider=mlx 缺少 Python 依赖 mlx-audio。\n"
                "  修复：pip install mlx-audio（仅 Apple Silicon 可安装）\n"
                "  或改用：export TTS_PROVIDER=openai\n"
                f"  {DOC_HINT}"
            )
        return True, f"mlx 就绪（module_dir={self.module_dir(self.block.get('narration_module') or 'generate_qa_video')}, model_root={root}）"

    # ── 模块加载 ──
    def _load_module(self, module_name):
        d = self.module_dir(module_name)
        if d not in sys.path:
            sys.path.insert(0, d)
        try:
            return __import__(module_name)
        except Exception as exc:  # noqa: BLE001
            raise TtsRuntimeError(
                f"provider=mlx 加载 {module_name} 失败（{type(exc).__name__}: {exc}）。\n"
                f"  模块目录：{d}\n"
                f"  常见原因：mlx-audio 未安装 / 模型权重缺失 / 该目录下脚本自身路径硬编码不匹配。\n"
                f"  诊断：python3 scripts/doctor.py --tts\n  {DOC_HINT}"
            ) from exc

    def synthesize(self, text, out_path, role="answer", emotion=None, work_dir=None) -> dict:
        ok, why = self.ready()
        if not ok:
            raise TtsConfigError(why)
        out_path = os.path.abspath(out_path)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

        if emotion:
            # 片尾口播：与原 append_epilogue.py 的 batch_tts 调用逐参数一致
            mod = self._load_module(self.block.get("epilogue_module") or "generate_news_card_video")
            entry = self.block.get("epilogue_entry") or "batch_tts"
            work = work_dir or os.path.dirname(out_path) or "."
            os.makedirs(work, exist_ok=True)
            fn = getattr(mod, entry, None)
            if fn is None:
                raise TtsRuntimeError(f"provider=mlx：{mod.__name__} 缺少入口 {entry}()；{DOC_HINT}")
            fn([(text, out_path)], work, emotion)
        else:
            # 旁白逐句：与原 story build_audio.py 的 generate_qwen3_tts(text, out, role) 一致
            mod = self._load_module(self.block.get("narration_module") or "generate_qa_video")
            entry = self.block.get("narration_entry") or "generate_qwen3_tts"
            fn = getattr(mod, entry, None)
            if fn is None:
                raise TtsRuntimeError(f"provider=mlx：{mod.__name__} 缺少入口 {entry}()；{DOC_HINT}")
            fn(text, out_path, role or self.voice_role())

        if not os.path.isfile(out_path):
            raise TtsRuntimeError(f"provider=mlx 未产出音频文件：{out_path}（合成失败）")
        return {
            "provider": self.name,
            "engine": "Qwen3-TTS (mlx_audio) via %s" % (self.block.get("narration_module") or "generate_qa_video"),
            "out": out_path,
            "sample_rate": self.block.get("sample_rate", 24000),
            "channels": self.block.get("channels", 1),
        }


class _OpenAIProvider(_BaseProvider):
    name = "openai"

    def _env(self, key, default=""):
        return os.environ.get(key, "").strip() or default

    def base_url(self) -> str:
        return self._env(self.block.get("base_url_env") or "TTS_BASE_URL").rstrip("/")

    def api_key(self) -> str:
        # 凭据只读环境变量：不落盘、不写日志、不回显
        return os.environ.get(self.block.get("api_key_env") or "TTS_API_KEY", "").strip()

    def model(self) -> str:
        return self._env(self.block.get("model_env") or "TTS_MODEL")

    def voice(self, emotion=None) -> str:
        if emotion:
            key = "TTS_VOICE_" + str(emotion).upper().replace("-", "_")
            if self._env(key):
                return self._env(key)
            mapping = self.block.get("voice_by_emotion") or {}
            if emotion in mapping:
                v = _expand(mapping[emotion]) if mapping[emotion] else ""
                if v:
                    return v
        return self._env(self.block.get("voice_env") or "TTS_VOICE")

    def response_format(self) -> str:
        return self._env(self.block.get("response_format_env") or "TTS_RESPONSE_FORMAT",
                         str(self.block.get("response_format") or "wav"))

    def speed(self) -> float:
        raw = self._env(self.block.get("speed_env") or "TTS_SPEED")
        try:
            return float(raw) if raw else float(self.block.get("speed") or 1.0)
        except ValueError:
            raise TtsConfigError(f"TTS_SPEED 必须是数字，当前={raw!r}；{DOC_HINT}")

    def timeout(self) -> float:
        raw = self._env(self.block.get("timeout_env") or "TTS_TIMEOUT_S")
        try:
            return float(raw) if raw else float(self.block.get("timeout_s") or 120)
        except ValueError:
            raise TtsConfigError(f"TTS_TIMEOUT_S 必须是数字，当前={raw!r}；{DOC_HINT}")

    def extra_headers(self) -> dict:
        raw = self._env(self.block.get("extra_headers_env") or "TTS_EXTRA_HEADERS")
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("必须是 JSON object")
            return {str(k): str(v) for k, v in data.items()}
        except Exception as exc:  # noqa: BLE001
            raise TtsConfigError(
                f"{self.block.get('extra_headers_env') or 'TTS_EXTRA_HEADERS'} 必须是 JSON object，"
                f"当前解析失败（{exc}）；{DOC_HINT}"
            )

    def ready(self):
        base = self.base_url()
        missing = []
        if not base:
            missing.append("TTS_BASE_URL（形如 https://api.openai.com/v1）")
        if not self.api_key():
            missing.append("TTS_API_KEY（凭据只读环境变量，禁止写入仓库文件）")
        if not self.model():
            missing.append("TTS_MODEL（如 tts-1 / gpt-4o-mini-tts / 兼容服务模型名）")
        if not self.voice():
            missing.append("TTS_VOICE（如 alloy / zh-CN-XiaoxiaoNeural）")
        if missing:
            return False, (
                "provider=openai 配置不完整，缺失：\n    - " + "\n    - ".join(missing) +
                "\n  示例（macOS/Linux）：\n"
                "    export TTS_BASE_URL=https://api.openai.com/v1\n"
                "    export TTS_API_KEY=<你的密钥>\n"
                "    export TTS_MODEL=gpt-4o-mini-tts\n"
                "    export TTS_VOICE=alloy\n"
                "  Windows PowerShell：$env:TTS_BASE_URL=\"...\"  （其余同）\n"
                f"  注意：未配置时本链路直接失败，不会静默降级到 mlx。\n  {DOC_HINT}"
            )
        return True, f"openai 就绪（endpoint={base}/audio/speech, model={self.model()}, voice={self.voice()}）"

    def synthesize(self, text, out_path, role="answer", emotion=None, work_dir=None) -> dict:
        ok, why = self.ready()
        if not ok:
            raise TtsConfigError(why)
        out_path = os.path.abspath(out_path)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

        fmt = self.response_format()
        body = {
            "model": self.model(),
            "input": text,
            "voice": self.voice(emotion),
            "response_format": fmt,
            "speed": self.speed(),
        }
        headers = {
            "Authorization": "Bearer " + self.api_key(),
            "Content-Type": "application/json",
            "Accept": "*/*",
        }
        headers.update(self.extra_headers())
        req = urllib.request.Request(
            self.base_url() + "/audio/speech",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout()) as resp:
                payload = resp.read()
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:800]
            except Exception:  # noqa: BLE001
                pass
            raise TtsRuntimeError(
                f"云端 TTS 返回 HTTP {exc.code}（{self.base_url()}/audio/speech）。\n"
                f"  服务端响应：{detail or '(空)'}\n"
                f"  排查：base_url 是否含 /v1、model/voice 是否为该服务支持、TTS_API_KEY 是否有效与有余额。\n"
                f"  {DOC_HINT}"
            ) from exc
        except urllib.error.URLError as exc:
            raise TtsRuntimeError(
                f"云端 TTS 连接失败：{exc.reason}\n"
                f"  endpoint={self.base_url()}/audio/speech\n"
                f"  排查：网络/代理是否可达、base_url 拼写、TTS_TIMEOUT_S（当前 {self.timeout()}s）。\n"
                f"  {DOC_HINT}"
            ) from exc
        if not payload:
            raise TtsRuntimeError(f"云端 TTS 返回空内容（endpoint={self.base_url()}/audio/speech）；{DOC_HINT}")

        with open(out_path, "wb") as f:
            f.write(payload)
        return {
            "provider": self.name,
            "engine": f"OpenAI-compatible TTS ({self.model()})",
            "out": out_path,
            "response_format": fmt,
            "elapsed_s": round(time.time() - t0, 2),
            "sample_rate": self.block.get("sample_rate", 24000),
            "channels": self.block.get("channels", 1),
        }


_REGISTRY = {"mlx": _MlxProvider, "openai": _OpenAIProvider}


def get_provider(cfg=None, name=None):
    cfg = cfg or load_config()
    name = (name or provider_name(cfg)).lower()
    if name not in _REGISTRY:
        raise TtsConfigError(f"未知 TTS provider：{name!r}；可选：{', '.join(VALID_PROVIDERS)}")
    return _REGISTRY[name](cfg)


def probe(cfg=None, name=None):
    """配置自检：返回 (ok, 说明)。不联网、不加载模型。"""
    try:
        prov = get_provider(cfg, name)
    except TtsConfigError as exc:
        return False, str(exc)
    try:
        return prov.ready()
    except Exception as exc:  # noqa: BLE001
        return False, f"{prov.name} 自检异常：{type(exc).__name__}: {exc}"


def synthesize(text, out_path, role="answer", emotion=None, work_dir=None, cfg=None, provider=None) -> dict:
    """统一合成入口：按配置分派 provider。未配置 → 抛 TtsConfigError（不静默降级）。"""
    prov = get_provider(cfg, provider)
    return prov.synthesize(text, out_path, role=role, emotion=emotion, work_dir=work_dir)


def describe(cfg=None) -> str:
    name = provider_name(cfg)
    ok, why = probe(cfg, name)
    state = "就绪" if ok else "未就绪"
    return f"TTS provider={name}（{state}）{why}"


if __name__ == "__main__":
    # CLI 语义：就绪 → 0（stdout 首行 = provider 摘要）；未就绪 → 1（stderr 给出修复指引）。
    # 供 storyctl build 的 TTS 前置闸门与 doctor.py 复用（只读、不联网）。
    _cfg = load_config()
    try:
        _name = provider_name(_cfg)
        _ok, _why = probe(_cfg, _name)
        _line = f"TTS provider={_name}（{'就绪' if _ok else '未就绪'}）{_why}"
    except TtsConfigError as _exc:
        _ok, _line = False, f"TTS 配置错误：{_exc}"
    if _ok:
        print(_line)
        sys.exit(0)
    print(_line, file=sys.stderr)
    sys.exit(1)
