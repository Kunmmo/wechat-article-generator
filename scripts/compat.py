"""
跨平台兼容性工具

提供 Windows / macOS 环境下的 UTF-8 一致性保证和平台诊断信息。
所有 CLI 入口点应在启动时调用 ensure_utf8_env()。
"""

import locale
import os
import sys


def ensure_utf8_env() -> None:
    """
    确保进程以 UTF-8 模式运行。

    Windows 默认 locale 可能是 GBK/cp936，导致中文内容读写乱码。
    此函数设置 PYTHONUTF8=1 并将 stdout/stderr 重新配置为 UTF-8。
    macOS / Linux 通常已是 UTF-8，此函数为 no-op。
    """
    if sys.platform == "win32":
        os.environ.setdefault("PYTHONUTF8", "1")
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                try:
                    stream.reconfigure(encoding="utf-8")
                except Exception:
                    pass


def get_platform_info() -> dict:
    """
    返回当前平台诊断信息，用于日志记录。

    AI 编程智能体可据此判断运行环境差异。
    """
    return {
        "os": sys.platform,
        "python": sys.version,
        "encoding": locale.getpreferredencoding(),
        "utf8_mode": bool(os.environ.get("PYTHONUTF8")),
    }
