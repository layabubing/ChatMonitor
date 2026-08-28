"""
用户仓储：注册/查询/管理员种子/改密/改昵称/密码校验。
纯持久化 + 密码哈希，不涉及 JWT/Cookie（那是 web/auth 的职责）。
"""
from __future__ import annotations

import hmac
import json
import secrets
import sqlite3
import time

from config import get_app_config
from core.accounts import db

ROLE_ADMIN = "admin"
ROLE_USER = "user"
SALT_DEFAULT = "chat-monitor-salt-v1"


def create_user(username: str, password: str, role: str = ROLE_USER) -> tuple[bool, str]:
    """创建用户；返回 (成功?, 消息)。新用户附带默认关键词库（从全局模板复制）。"""
    username = (username or "").strip()
    if not (3 <= len(username) <= 32):
        return False, "用户名长度需 3-32 个字符"
    if len(password) < 6:
        return False, "密码至少 6 位"
    salt = secrets.token_hex(8)
    with db.lock, db.connect() as conn:
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, role, password_version, created_at) "
                "VALUES (?,?,?,?,1,?)",
                (username, db.hash_password(password, salt), salt, role, int(time.time() * 1000)),
            )
            conn.commit()
            _seed_default_keywords(conn, username)
            return True, "注册成功"
        except sqlite3.IntegrityError:
            return False, "用户名已存在"


def _seed_default_keywords(conn: sqlite3.Connection, username: str) -> None:
    """新用户初始化默认关键词库（从全局默认模板复制，作为独立起点）。缺失不影响注册。"""
    try:
        from config import CONFIGS_DIR
        default = json.loads((CONFIGS_DIR / "important_keywords.json").read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO user_keywords (username, categories, updated_at) VALUES (?,?,?)",
            (username, json.dumps(default, ensure_ascii=False), int(time.time() * 1000)),
        )
        conn.commit()
    except Exception:  # noqa: BLE001
        pass


def find_user(username: str) -> sqlite3.Row | None:
    with db.connect() as conn:
        return conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()


def ensure_admin() -> None:
    """确保 admin 账号存在：用 app.env 的凭证作为种子（不存在则创建）。"""
    cfg = get_app_config()
    admin_name = cfg.get("ADMIN_USERNAME", "admin")
    existing = find_user(admin_name)
    if existing:
        if existing["role"] != ROLE_ADMIN:
            with db.lock, db.connect() as conn:
                conn.execute("UPDATE users SET role=? WHERE username=?", (ROLE_ADMIN, admin_name))
                conn.commit()
        return
    pwd = cfg.get("ADMIN_PASSWORD", "change-me-please")
    salt = cfg.get("ADMIN_PASSWORD_SALT") or SALT_DEFAULT
    stored_hash = cfg.get("ADMIN_PASSWORD_HASH") or db.hash_password(pwd, salt)
    with db.lock, db.connect() as conn:
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, role, created_at) VALUES (?,?,?,?,?)",
                (admin_name, stored_hash, salt, ROLE_ADMIN, int(time.time() * 1000)),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass


def verify_password(username: str, password: str) -> bool:
    """校验密码是否正确（不签发 token），用于登录与改密时的旧密码验证。"""
    user = find_user((username or "").strip())
    if not user or not password:
        return False
    return hmac.compare_digest(db.hash_password(password, user["salt"]), user["password_hash"])


def update_password(username: str, new_password: str) -> bool:
    """修改指定用户密码（password_version+1，使旧 token 失效）。"""
    if len(new_password) < 6:
        return False
    salt = secrets.token_hex(8)
    with db.lock, db.connect() as conn:
        cur = conn.execute(
            "UPDATE users SET password_hash=?, salt=?, password_version=password_version+1 WHERE username=?",
            (db.hash_password(new_password, salt), salt, username),
        )
        conn.commit()
        return cur.rowcount > 0


def update_nickname(username: str, nickname: str) -> bool:
    """修改用户昵称（仅本人可用；空昵称回退为用户名）。"""
    nickname = (nickname or "").strip()
    if len(nickname) > 24:
        return False
    with db.lock, db.connect() as conn:
        cur = conn.execute("UPDATE users SET nickname=? WHERE username=?", (nickname, username))
        conn.commit()
        return cur.rowcount > 0


def count_users() -> int:
    with db.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def list_users() -> list[dict]:
    """列出全部用户（SSE 轮询扫描用）。"""
    with db.connect() as conn:
        rows = conn.execute("SELECT username, role FROM users ORDER BY id").fetchall()
    return [{"username": r["username"], "role": r["role"]} for r in rows]
