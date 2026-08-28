"""
控制台输出兼容：Windows 默认 GBK 控制台无法输出 emoji（⚠ 等）会抛
UnicodeEncodeError 导致进程崩溃。入口处调用 setup() 将 stdout/stderr
切到 UTF-8（errors=replace），保证日志健壮不中断业务。
"""
from __future__ import annotations

import sys


def setup() -> None:
    """将标准输出/错误切换为 UTF-8，无法编码的字符以占位符替代（幂等、失败静默）。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001  控制台不支持时忽略
            pass
