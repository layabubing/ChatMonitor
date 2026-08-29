"""
.env 文件安全更新工具（网页端账号绑定用）
只允许白名单内的 KEY 被写入，防止任意键注入
"""
from __future__ import annotations

from pathlib import Path

from config import PLATFORM_META

# 各平台允许写入的配置键白名单（由 PLATFORM_META 注册表派生，新增平台自动生效）
PLATFORM_KEYS = {p: list(m["keys"]) for p, m in PLATFORM_META.items()}


def allowed_keys(platform: str) -> list[str]:
    return PLATFORM_KEYS.get(platform, [])


def _clean_value(v) -> str:
    """清洗 .env 写入值：去除换行/回车/控制字符，防止配置注入"""
    s = str(v).replace("\r", " ").replace("\n", " ")
    return "".join(ch for ch in s if ch == " " or ch.isprintable()).strip()


def update_env_file(path: Path, updates: dict) -> list[str]:
    """更新 .env：只保留白名单键；返回实际写入的键列表。保留注释与其他行。"""
    keys = set(updates)
    updates = {k: _clean_value(v) for k, v in updates.items()}
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    out: list[str] = []
    written: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k in keys:
                out.append(f"{k}={updates[k]}")
                written.add(k)
                continue
        out.append(line)
    for k, v in updates.items():
        if k not in written:
            out.append(f"{k}={v}")
            written.add(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    # 临时文件 + rename 原子写，防崩溃损坏 .env
    import os
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return sorted(written)
