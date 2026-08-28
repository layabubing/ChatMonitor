"""
用户级关键词库仓储（多租户）：每个用户维护自己的关键词分类。
（全局默认关键词模板见 core/keywords.py）
"""
from __future__ import annotations

import json
import time

from core.accounts import db


def get_user_keywords(username: str) -> dict:
    """读取用户自己的关键词库（未设置返回空）。"""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT categories FROM user_keywords WHERE username=?", (username,)
        ).fetchone()
    if not row:
        return {}
    try:
        return json.loads(row["categories"] or "{}")
    except Exception:  # noqa: BLE001
        return {}


def save_user_keywords(username: str, categories: dict) -> None:
    """保存用户关键词库（upsert）。"""
    with db.lock, db.connect() as conn:
        conn.execute(
            """INSERT INTO user_keywords (username, categories, updated_at)
               VALUES (?,?,?)
               ON CONFLICT(username)
               DO UPDATE SET categories=excluded.categories, updated_at=excluded.updated_at""",
            (username, json.dumps(categories, ensure_ascii=False), int(time.time() * 1000)),
        )
        conn.commit()


def flatten(categories: dict) -> list[str]:
    """把分类字典展开为去重保序的关键词列表。"""
    return list(dict.fromkeys(w for group in categories.values() for w in group))
