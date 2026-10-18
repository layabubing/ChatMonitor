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


# ── 绑定档案（历史版本）：支持一键切换回原绑定，配置不丢失 ──
def _row_to_profile(r) -> dict:
    return {
        "id": r["id"],
        "name": r["name"],
        "config": json.loads(r["config"] or "{}"),
        "enabled": bool(r["enabled"]),
        "created_at": r["created_at"],
        "last_used_at": r["last_used_at"],
    }


def save_profile(username: str, platform: str, name: str,
                 config: dict, enabled: bool = True) -> int:
    """保存/更新一条绑定档案（同名覆盖）。返回档案 id。"""
    now = int(time.time() * 1000)
    name = (name or "").strip() or f"档案 {time.strftime('%Y-%m-%d %H:%M')}"
    with db.lock, db.connect() as conn:
        conn.execute(
            """INSERT INTO binding_profiles
                   (username, platform, name, config, enabled, created_at, last_used_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(username, platform, name)
               DO UPDATE SET config=excluded.config, enabled=excluded.enabled,
                             last_used_at=excluded.last_used_at""",
            (username, platform, name, json.dumps(config, ensure_ascii=False),
             1 if enabled else 0, now, now),
        )
        row = conn.execute(
            "SELECT id FROM binding_profiles WHERE username=? AND platform=? AND name=?",
            (username, platform, name),
        ).fetchone()
        conn.commit()
    return int(row["id"]) if row else 0


def list_profiles(username: str, platform: str) -> list[dict]:
    """列出某用户某平台的全部绑定档案（最近使用的在前）。"""
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT id, name, config, enabled, created_at, last_used_at
               FROM binding_profiles WHERE username=? AND platform=?
               ORDER BY COALESCE(last_used_at, created_at) DESC, id DESC""",
            (username, platform),
        ).fetchall()
    return [_row_to_profile(r) for r in rows]


def get_profile(username: str, platform: str, profile_id: int) -> dict | None:
    """取单条绑定档案。"""
    with db.connect() as conn:
        row = conn.execute(
            """SELECT id, name, config, enabled, created_at, last_used_at
               FROM binding_profiles WHERE username=? AND platform=? AND id=?""",
            (username, platform, profile_id),
        ).fetchone()
    return _row_to_profile(row) if row else None


def delete_profile(username: str, platform: str, profile_id: int) -> bool:
    """删除绑定档案（仅限本人本平台）。"""
    with db.lock, db.connect() as conn:
        cur = conn.execute(
            "DELETE FROM binding_profiles WHERE username=? AND platform=? AND id=?",
            (username, platform, profile_id),
        )
        conn.commit()
    return cur.rowcount > 0


def archive_current(username: str, platform: str, prefix: str = "自动备份") -> int | None:
    """把「当前生效绑定」存为档案（切换前留底）。

    相同配置已存在时直接复用，避免每次保存都堆积一条重复档案。"""
    cur = get_user_binding(username, platform)
    if not cur or not cur.get("config"):
        return None
    cfg = cur["config"]
    for p in list_profiles(username, platform):
        if p["config"] == cfg:
            return int(p["id"])
    name = f"{prefix} {time.strftime('%Y-%m-%d %H:%M')}"
    return save_profile(username, platform, name, cfg, bool(cur.get("enabled", True)))


def activate_profile(username: str, platform: str, profile_id: int) -> dict | None:
    """切换到指定档案：先把当前配置留底，再完整写回当前绑定（config + enabled）。"""
    prof = get_profile(username, platform, profile_id)
    if not prof:
        return None
    archive_current(username, platform)   # 防丢：切换前把正在用的配置存为档案
    save_user_binding(username, platform, prof["config"], enabled=prof["enabled"])
    with db.lock, db.connect() as conn:
        conn.execute(
            "UPDATE binding_profiles SET last_used_at=? WHERE username=? AND platform=? AND id=?",
            (int(time.time() * 1000), username, platform, profile_id),
        )
        conn.commit()
    return prof
