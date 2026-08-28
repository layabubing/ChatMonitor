"""
用户级平台绑定仓储（多租户）：每个用户各自绑定 QQ/钉钉 凭证与开关。
"""
from __future__ import annotations

import json
import time

from core.accounts import db


def get_user_binding(username: str, platform: str) -> dict | None:
    """读取某用户某平台的绑定配置；未绑定返回 None。"""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT config, enabled FROM user_bindings WHERE username=? AND platform=?",
            (username, platform),
        ).fetchone()
    if not row:
        return None
    return {"config": json.loads(row["config"] or "{}"), "enabled": bool(row["enabled"])}


def save_user_binding(username: str, platform: str, config: dict, enabled: bool = True) -> None:
    """保存用户平台绑定（upsert）。"""
    with db.lock, db.connect() as conn:
        conn.execute(
            """INSERT INTO user_bindings (username, platform, config, enabled, updated_at)
               VALUES (?,?,?,?,?)
               ON CONFLICT(username, platform)
               DO UPDATE SET config=excluded.config, enabled=excluded.enabled, updated_at=excluded.updated_at""",
            (username, platform, json.dumps(config, ensure_ascii=False),
             1 if enabled else 0, int(time.time() * 1000)),
        )
        conn.commit()


def list_bound_users(platform: str) -> list[dict]:
    """列出某平台所有已启用绑定的用户（worker 扫描用）。"""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT username, config FROM user_bindings WHERE platform=? AND enabled=1",
            (platform,),
        ).fetchall()
    return [{"username": r["username"], "config": json.loads(r["config"] or "{}")} for r in rows]
