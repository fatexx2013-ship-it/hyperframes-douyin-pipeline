#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
platform_env.py —— 跨平台（macOS / Linux / Windows）环境适配层

职责
----
1. 可执行文件解析：环境变量 → PATH →「按平台」的常见安装目录回退。
   统一替代此前散落在各脚本里的 `/opt/homebrew/bin`、`/usr/local/bin`
   硬编码（macOS 专属）拼接。
2. 中文字体解析：按平台给出候选字体文件与字体族名。
   macOS = PingFang SC / Linux = Noto Sans CJK SC / Windows = Microsoft YaHei。
3. 环境变量覆盖口径（全部只读，不写入任何凭据）：

   | 环境变量 | 作用 |
   |---|---|
   | `<TOOL>`（大写，`-`→`_`） | 直接指定某工具可执行文件绝对路径，如 `FFMPEG=/usr/bin/ffmpeg` |
   | `FONT_FILE` | 直接指定字幕渲染用字体文件绝对路径 |
   | `STORY_FONT_FAMILY` | 直接指定 ASS/字幕字体族名 |
   | `STORY_EXTRA_PATH` | 追加搜索目录（`:` / `;` 分隔），排在最前 |

设计约束
--------
- 不改变任何产线参数值（分辨率为 1080×1920、fps=30、编码链均为不变量）。
- 找不到工具 / 字体时给出「明确可操作」的报错，绝不静默降级。

用法
----
    import platform_env
    ffmpeg = platform_env.require_tool("ffmpeg", purpose="终合成")
    font   = platform_env.require_font_file(purpose="drawtext 水印")
    family = platform_env.font_family()
    env    = platform_env.tool_env()     # PATH 已按平台补齐
"""

from __future__ import annotations

import glob
import os
import platform
import shutil
import sys

# ── 平台判定 ──────────────────────────────────────────────────────────────
IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

PLATFORM_ENV = "STORY_PLATFORM"
EXTRA_PATH_ENV = "STORY_EXTRA_PATH"
FONT_FILE_ENV = "FONT_FILE"
FONT_FAMILY_ENV = "STORY_FONT_FAMILY"

# 工具清单（顺序即 doctor 的检查顺序）
TOOL_CHAIN = ("python3", "ffmpeg", "ffprobe", "node", "npx", "whisper-cli", "hyperframes")


class ToolNotFound(RuntimeError):
    """工具缺失：报错信息必须可直接照抄执行。"""


class FontNotFound(RuntimeError):
    """字体缺失：报错信息必须给出各平台安装命令。"""


def platform_name() -> str:
    """返回 'macos' / 'linux' / 'windows' / 其它原值。"""
    if IS_MACOS:
        return "macos"
    if IS_LINUX:
        return "linux"
    if IS_WINDOWS:
        return "windows"
    return sys.platform


def is_apple_silicon() -> bool:
    """Apple Silicon（MLX 本地 TTS 的硬件前提）。"""
    if not IS_MACOS:
        return False
    return platform.machine().lower() in ("arm64", "aarch64")


# ── 可执行文件解析 ────────────────────────────────────────────────────────

def platform_bin_dirs() -> list:
    """按平台给出常见安装目录（仅回退用；PATH 命中时不会走到这里）。"""
    dirs = []
    extra = os.environ.get(EXTRA_PATH_ENV, "")
    if extra:
        dirs.extend([p for p in extra.replace(";", os.pathsep).split(os.pathsep) if p])

    if IS_MACOS:
        dirs += [
            # 历史产线使用 Homebrew ffmpeg-full（libass/fontconfig 等编解码全量），
            # 其路径优先于通用 ffmpeg，保持改造前行为不变。
            "/opt/homebrew/opt/ffmpeg-full/bin",
            "/opt/homebrew/bin",              # Apple Silicon Homebrew
            "/usr/local/opt/ffmpeg-full/bin",
            "/usr/local/bin",                 # Intel Homebrew / 手工安装
            "/opt/local/bin",                 # MacPorts
            "/usr/bin",
        ]
    elif IS_LINUX:
        dirs += [
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
            "/snap/bin",
            "/home/linuxbrew/.linuxbrew/bin",
            "/usr/local/ffmpeg/bin",
        ]
        home = os.path.expanduser("~")
        dirs += [
            os.path.join(home, ".local", "bin"),
            os.path.join(home, "bin"),
            "/usr/lib/winget/bin",
        ]
    elif IS_WINDOWS:
        home = os.path.expanduser("~")
        local = os.environ.get("LOCALAPPDATA", "")
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        dirs += [
            os.path.join(local, "Microsoft", "WinGet", "Links"),
            os.path.join(pf, "ffmpeg", "bin"),
            os.path.join(pf86, "ffmpeg", "bin"),
            os.path.join(pf, "nodejs"),
            os.path.join(pf, "hyperframes"),
            os.path.join(home, "scoop", "shims"),
            os.path.join(home, "AppData", "Local", "Programs", "Python", "Scripts"),
            os.path.join(home, ".local", "bin"),
            r"C:\ffmpeg\bin",
            r"C:\tools\ffmpeg\bin",
        ]
    # 去重（保序）
    seen, out = set(), []
    for d in dirs:
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def _names_for(name: str) -> list:
    """Windows 下补 .exe / .cmd / .bat 变体。"""
    if "." in os.path.basename(name):
        return [name]
    if IS_WINDOWS:
        return [name + ext for ext in (".exe", ".cmd", ".bat")] + [name]
    return [name]


def _is_exec(p: str) -> bool:
    return bool(p) and os.path.isfile(p) and os.access(p, os.X_OK)


def _env_keys_for(name: str) -> list:
    """工具覆盖用的环境变量名（按优先级）：
    `PIPELINE_<TOOL>` 命名空间优先，其次 `<TOOL>` 裸名（兼容既有习惯）。"""
    key = name.upper().replace("-", "_").replace(".", "_")
    return [f"PIPELINE_{key}", key]


def find_tool(name: str):
    """解析可执行文件：环境变量 → PATH → 平台常见目录。找不到返回 None。

    环境变量覆盖：`PIPELINE_<TOOL>`（推荐，避免与系统同名变量打架）或 `<TOOL>`
    （如 `PIPELINE_FFMPEG` / `FFMPEG`、`PIPELINE_WHISPER_CLI` / `WHISPER_CLI`）。
    """
    if os.sep in name or "/" in name:          # 已给路径
        return name if _is_exec(name) else None

    for env_key in _env_keys_for(name):
        env_val = os.environ.get(env_key, "").strip()
        if env_val:
            if _is_exec(env_val):
                return env_val
            # 显式指定却不可执行 = 配置错误，直接暴露（不静默回退）
            raise ToolNotFound(
                f"环境变量 {env_key}={env_val!r} 指向的文件不存在或不可执行。\n"
                f"  请修正该环境变量，或清空它以改为自动查找（PATH / 平台常见目录）。"
            )

    for cand in _names_for(name):
        hit = shutil.which(cand)
        if hit:
            return hit
    for d in platform_bin_dirs():
        for cand in _names_for(name):
            p = os.path.join(d, cand)
            if _is_exec(p):
                return p
    return None


def require_tool(name: str, purpose: str = "") -> str:
    """必须存在的工具；缺失即抛错，报错含各平台安装提示。"""
    hit = find_tool(name)
    if hit:
        return hit
    why = f"（用途：{purpose}）" if purpose else ""
    raise ToolNotFound(
        f"找不到可执行文件 {name}{why}。\n"
        f"  1) 安装：macOS `brew install {name}` / Debian-Ubuntu `sudo apt install {name}` / "
        f"Windows `winget install {name}`（或 scoop/choco）；\n"
        f"  2) 或把 {name} 所在目录加入 PATH；\n"
        f"  3) 或显式指定：export PIPELINE_{name.upper().replace('-', '_')}=/绝对/路径/{name}"
        f"（也兼容裸名 {name.upper().replace('-', '_')}）；\n"
        f"  4) 自检：python3 scripts/doctor.py\n"
        f"  详见 docs/DEPLOY.md。"
    )


def tool_env(base=None) -> dict:
    """返回 PATH 已按平台补齐的环境变量副本（替代旧 brew_env）。"""
    env = dict(os.environ if base is None else base)
    parts = [p for p in platform_bin_dirs() if os.path.isdir(p)]
    cur = env.get("PATH", "")
    env["PATH"] = os.pathsep.join(parts + ([cur] if cur else []))
    return env


# 旧名兼容：历史脚本调用 brew_env()
def brew_env() -> dict:  # noqa: D401
    return tool_env()


# 旧名兼容：历史脚本调用 ensure_brew_path()（原地把平台 bin 目录并入 PATH）
def ensure_brew_path() -> None:  # noqa: D401
    """把工具链常见目录并入 os.environ['PATH']（原地修改；旧 workaround 的跨平台替代）。"""
    os.environ["PATH"] = tool_env()["PATH"]


# ── 中文字体解析 ──────────────────────────────────────────────────────────

_MAC_FONT_CANDIDATES = [
    "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/*/AssetData/PingFang.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Supplemental/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/Library/Fonts/PingFang.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]

_LINUX_FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/**/NotoSansCJK*Regular*.ttc",
    "/usr/share/fonts/**/NotoSansSC*Regular*.otf",
    "/usr/share/fonts/**/SourceHanSansSC*Regular*.otf",
    "/usr/share/fonts/**/msyh*.tt*",
]

_WINDOWS_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\Deng.ttf",
    r"C:\Windows\Fonts\Dengb.ttf",
    r"C:\Windows\Fonts\msyh.ttf",
]

_FONT_FAMILY_BY_PLATFORM = {
    "macos": "PingFang SC",
    "linux": "Noto Sans CJK SC",
    "windows": "Microsoft YaHei",
}


def font_candidates() -> list:
    """按平台给出候选字体路径（支持 glob），环境变量 FONT_FILE 排最前。"""
    cands = []
    explicit = os.environ.get(FONT_FILE_ENV, "").strip()
    if explicit:
        cands.append(explicit)
    if IS_MACOS:
        cands += _MAC_FONT_CANDIDATES
    elif IS_LINUX:
        cands += _LINUX_FONT_CANDIDATES
    elif IS_WINDOWS:
        cands += _WINDOWS_FONT_CANDIDATES
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            cands.append(os.path.join(local, "Microsoft", "Windows", "Fonts", "*.tt*"))
    else:
        cands += _MAC_FONT_CANDIDATES + _LINUX_FONT_CANDIDATES
    return cands


def find_font_file(explicit=None):
    """返回第一个可用的中文字体文件路径；找不到返回 None。"""
    cands = ([explicit] if explicit else []) + font_candidates()
    for pat in cands:
        for p in sorted(glob.glob(pat)):
            if os.path.isfile(p):
                return p
    return None


def require_font_file(explicit=None, purpose: str = "") -> str:
    """必须存在的中文字体；缺失抛出可直接照抄的安装指引。"""
    hit = find_font_file(explicit)
    if hit:
        return hit
    why = f"（用途：{purpose}）" if purpose else ""
    raise FontNotFound(
        f"找不到可用的中文字体{why}。\n"
        f"  1) 安装：macOS 自带 PingFang SC；Debian-Ubuntu `sudo apt install fonts-noto-cjk`"
        f"（或 fonts-wqy-zenhei）；Windows 自带 Microsoft YaHei；\n"
        f"  2) 或显式指定字体文件：export {FONT_FILE_ENV}=/绝对/路径/字体.ttc；\n"
        f"  3) 自检：python3 scripts/doctor.py\n"
        f"  详见 docs/DEPLOY.md。"
    )


def font_family() -> str:
    """字幕/ASS 使用的字体族名（环境变量 STORY_FONT_FAMILY 优先）。"""
    env_val = os.environ.get(FONT_FAMILY_ENV, "").strip()
    if env_val and env_val.lower() != "auto":
        return env_val
    return _FONT_FAMILY_BY_PLATFORM.get(platform_name(), "PingFang SC")


# ── 自检输出 ──────────────────────────────────────────────────────────────

def describe() -> str:
    """一行摘要，便于写进日志/报告。"""
    return (f"platform={platform_name()} machine={platform.machine()} "
            f"apple_silicon={is_apple_silicon()} font_family={font_family()}")


def _cli(argv) -> int:
    """轻量 CLI（供 shell 脚本取跨平台解析结果，避免在 .sh 里写死 macOS 路径）：

        python3 scripts/platform_env.py tool ffmpeg      # 打印绝对路径，找不到则空
        python3 scripts/platform_env.py font-family      # 打印字体族名
        python3 scripts/platform_env.py font-file        # 打印字体文件绝对路径
        python3 scripts/platform_env.py platform         # macos / linux / windows
        python3 scripts/platform_env.py doctor           # 工具链 + 字体自检
    """
    if not argv:
        print(describe())
        for t in TOOL_CHAIN:
            print(f"  [{'OK ' if find_tool(t) else 'MISS'}] {t:<12} {find_tool(t) or '-'}")
        print(f"  font file = {find_font_file() or '-'}")
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "tool":
        if not rest:
            print("用法: platform_env.py tool <name>", file=sys.stderr)
            return 2
        hit = find_tool(rest[0])
        if hit:
            print(hit)
            return 0
        return 1
    if cmd == "font-family":
        print(font_family())
        return 0
    if cmd == "font-file":
        hit = find_font_file()
        if hit:
            print(hit)
            return 0
        return 1
    if cmd == "platform":
        print(platform_name())
        return 0
    if cmd == "doctor":
        missing = [t for t in TOOL_CHAIN if not find_tool(t)]
        print(describe())
        for t in TOOL_CHAIN:
            print(f"  [{'OK ' if find_tool(t) else 'MISS'}] {t:<12} {find_tool(t) or '-'}")
        print(f"  font file = {find_font_file() or '-'}")
        return 0 if not missing else 1
    print(f"未知子命令: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
