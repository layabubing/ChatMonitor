"""
命令通道：Web UI 写命令文件 → worker 轮询消费
文件格式: data/commands/{platform}.json  ({"cmd": "...", "payload": {...}, "ts": ...})
多租户：用户名指定时使用 data/commands/{platform}__{username}.json，互不覆盖
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from config import COMMANDS_DIR


def _path(platform: str, username: str = "") -> Path:
    if username:
        return COMMANDS_DIR / f"{platform}__{username}.json"
    return COMMANDS_DIR / f"{platform}.json"


def write_command(platform: str, cmd: str, payload: dict | None = None,
                  username: str = "") -> None:
    """UI/控制端调用：下发一条命令（覆盖式，同刻只保留一条；带 username 时按用户隔离）"""
    COMMANDS_DIR.mkdir(parents=True, exist_ok=True)
    data = {"cmd": cmd, "payload": payload or {}, "ts": int(time.time())}
    _path(platform, username).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def consume_commands(platform: str, username: str = "") -> list[dict]:
    """worker 调用：消费并清空命令文件，返回命令列表（清空而非删除，更健壮）"""
    p = _path(platform, username)
    if not p.exists():
        return []
    try:
        raw = p.read_text(encoding="utf-8")
        p.write_text("", encoding="utf-8")   # 消费后清空内容
        if not raw.strip():
            return []
        data = json.loads(raw)
        return [data] if isinstance(data, dict) else (data if isinstance(data, list) else [])
    except Exception:
        try:
            p.write_text("", encoding="utf-8")
        except Exception:
            pass
        return []


def get_pending(platform: str, username: str = "") -> dict | None:
    """web 查询：当前是否有待执行命令（只读，不消费）"""
    p = _path(platform, username)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
