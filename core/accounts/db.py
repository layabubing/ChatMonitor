"""
账户存储底层：users.db 连接、schema、密码哈希。
被 users / bindings / keywords 三个仓储共享（单库、单写锁）。
"""
from __future__ import annotations

import hashlib
import sqlite3
import threading
from pathlib import Path

from config import DATA_DIR

# 跨仓储共享的写锁（users/bindings/keywords 同一个 users.db）
lock = threading.Lock()

_db_path: Path | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    password_version INTEGER DEFAULT 1,
    nickname TEXT DEFAULT '',
    created_at INTEGER
);
CREATE TABLE IF NOT EXISTS user_bindings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    platform TEXT NOT NULL,
    config TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER DEFAULT 0,
    updated_at INTEGER,
    UNIQUE(username, platform)
);
CREATE TABLE IF NOT EXISTS user_keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    categories TEXT NOT NULL DEFAULT '{}',
    updated_at INTEGER
);
"""


def set_store_path(path: str | Path) -> None:
    """测试/定制用：覆盖用户库路径"""
    global _db_path
    _db_path = Path(path)


def store_path() -> Path:
    global _db_path
    if _db_path is None:
        _db_path = DATA_DIR / "users.db"
    return _db_path


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """幂等迁移：为旧库补充新列"""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "password_version" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN password_version INTEGER DEFAULT 1")
    if "nickname" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN nickname TEXT DEFAULT ''")


def connect() -> sqlite3.Connection:
    p = store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # mode=rwc 读写 + 允许创建（避免 Windows 沙箱/权限环境默认只读打开；新库自动建）
    conn = sqlite3.connect(f"file:{p}?mode=rwc", uri=True, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)  # 幂等（多条 CREATE TABLE IF NOT EXISTS）
    _ensure_columns(conn)
    conn.commit()
    return conn


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
