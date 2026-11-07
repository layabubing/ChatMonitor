"""
存储基类：SQLite 连接、schema、跨表概览。
每平台/每租户独立 .db 文件；DELETE 日志模式避免受限目录下 WAL 锁/只读问题。
"""
from __future__ import annotations

import datetime
import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    msg_id     TEXT PRIMARY KEY,
    platform   TEXT NOT NULL,
    group_id   TEXT DEFAULT '',
    group_name TEXT DEFAULT '',
    sender     TEXT DEFAULT '',
    content    TEXT DEFAULT '',
    msg_type   TEXT DEFAULT 'text',
    media_urls TEXT DEFAULT '[]',
    ts         INTEGER NOT NULL,
    is_important INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS alerts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    platform   TEXT NOT NULL,
    msg_id     TEXT DEFAULT '',
    content    TEXT DEFAULT '',
    reason     TEXT DEFAULT '',
    suggestion TEXT DEFAULT '',
    priority   TEXT DEFAULT 'medium',
    sender     TEXT DEFAULT '',
    group_name TEXT DEFAULT '',
    ts         INTEGER NOT NULL,
    is_read    INTEGER DEFAULT 0,
    UNIQUE(platform, msg_id)
);
CREATE TABLE IF NOT EXISTS reports (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    platform   TEXT NOT NULL,
    date       TEXT NOT NULL,
    summary    TEXT DEFAULT '',
    docx_path  TEXT DEFAULT '',
    html_path  TEXT DEFAULT '',
    msg_count  INTEGER DEFAULT 0,
    important_count INTEGER DEFAULT 0,
    created_at INTEGER,
    UNIQUE(platform, date)
);
CREATE TABLE IF NOT EXISTS cursor (
    platform TEXT PRIMARY KEY,
    value    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    platform   TEXT NOT NULL,
    msg_id     TEXT DEFAULT '',
    local_path TEXT NOT NULL,
    orig_name  TEXT DEFAULT '',
    ftype      TEXT DEFAULT 'other',
    ext        TEXT DEFAULT '',
    size       INTEGER DEFAULT 0,
    important  INTEGER DEFAULT 0,
    ai_desc    TEXT DEFAULT '',
    category   TEXT DEFAULT '',
    ts         INTEGER NOT NULL,
    UNIQUE(platform, local_path)
);
CREATE INDEX IF NOT EXISTS idx_files_platform_ts ON files(platform, ts);
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts);
CREATE INDEX IF NOT EXISTS idx_messages_platform_ts ON messages(platform, ts);
CREATE INDEX IF NOT EXISTS idx_alerts_platform_ts ON alerts(platform, ts);
CREATE TABLE IF NOT EXISTS analysis_jobs (
    msg_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at REAL NOT NULL DEFAULT 0,
    receipt TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(msg_id, kind, target)
);
CREATE INDEX IF NOT EXISTS idx_analysis_due ON analysis_jobs(state, available_at);
CREATE TABLE IF NOT EXISTS report_tasks (
    platform TEXT NOT NULL,
    date TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at REAL NOT NULL DEFAULT 0,
    receipt TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(platform, date)
);
"""


class StorageBase:
    """连接管理 + 建表；各表仓储 Mixin 共享 _connect/_lock。"""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        conn = self._connect()
        try:
            conn.executescript(SCHEMA)
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.commit()
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        # mode=rwc：读写 + 允许创建（新用户首次访问自动建库；避免默认只读打开）
        conn = sqlite3.connect(f"file:{self.db_path}?mode=rwc", uri=True, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    # ── 跨表最大值（SSE 轮询专用，一次连接替代 4 次查询）──
    def max_ids(self, platform: str) -> dict:
        """一次连接取四类最大值：消息 ts / 提醒 id / 报告 id / 文件 id。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT (SELECT MAX(ts) FROM messages WHERE platform=?),"
                " (SELECT MAX(id) FROM alerts WHERE platform=?),"
                " (SELECT MAX(id) FROM reports WHERE platform=?),"
                " (SELECT MAX(id) FROM files WHERE platform=?)",
                (platform, platform, platform, platform),
            ).fetchone()
        return {
            "msg": int(row[0] or 0),
            "alert": int(row[1] or 0),
            "report": int(row[2] or 0),
            "file": int(row[3] or 0),
        }

    # ── 跨表概览 ──
    def overview(self) -> dict:
        today = datetime.date.today().isoformat()
        with self._connect() as conn:
            msg_total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            alert_total = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
            alert_unread = conn.execute("SELECT COUNT(*) FROM alerts WHERE is_read=0").fetchone()[0]
            report = conn.execute("SELECT * FROM reports ORDER BY date DESC LIMIT 1").fetchone()
        return {
            "msg_total": msg_total,
            "alert_total": alert_total,
            "alert_unread": alert_unread,
            "last_report": dict(report) if report else None,
            "today": today,
        }
