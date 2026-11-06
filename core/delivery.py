"""Durable callback deliveries, with one receipt per application and subscriber.

Acknowledged rows are retained to deduplicate callback retries. A lease recovers
deliveries after a worker crash; acknowledgement happens only after durable ingest.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager

import config


@contextmanager
def _connect():
    root = config.DATA_DIR / "inbox"
    root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(root / "deliveries.db", timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS deliveries (
            platform TEXT NOT NULL, corpid TEXT NOT NULL, agent_id TEXT NOT NULL,
            recipient TEXT NOT NULL, msg_id TEXT NOT NULL, payload TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending', available_at REAL NOT NULL DEFAULT 0,
            receipt TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(platform, corpid, agent_id, recipient, msg_id))""")
        conn.execute("""CREATE INDEX IF NOT EXISTS idx_delivery_pending
            ON deliveries(platform, corpid, agent_id, recipient, state, available_at)""")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def enqueue(platform: str, message: dict, recipients: list[str]) -> bool:
    """Atomically fan out to all subscribers, including duplicate callback retries."""
    if not message.get("msg_id") or not recipients:
        return False
    payload = json.dumps(message, ensure_ascii=False)
    with _connect() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO deliveries "
            "(platform, corpid, agent_id, recipient, msg_id, payload) VALUES (?,?,?,?,?,?)",
            [(platform, str(message.get("corpid", "")), str(message.get("agent_id", "")),
              recipient, str(message["msg_id"]), payload) for recipient in set(recipients)],
        )
    return True


def claim(platform: str, corpid: str, agent_id: str, recipient: str,
          lease_seconds: float = 300) -> dict | None:
    """Claim exactly one subscription's delivery. Expired leases are reclaimable."""
    now = time.time()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT rowid, payload FROM deliveries WHERE platform=? AND corpid=? "
            "AND agent_id=? AND recipient=? AND state!='done' AND available_at<=? "
            "ORDER BY rowid LIMIT 1", (platform, corpid, agent_id, recipient, now),
        ).fetchone()
        if row is None:
            return None
        receipt = uuid.uuid4().hex
        conn.execute("UPDATE deliveries SET state='processing', receipt=?, available_at=?, "
                     "attempts=attempts+1 WHERE rowid=?", (receipt, now + lease_seconds, row["rowid"]))
        return {"receipt": receipt, "message": json.loads(row["payload"])}


def acknowledge(receipt: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("UPDATE deliveries SET state='done', payload='{}', receipt='' "
                           "WHERE receipt=? AND state='processing'", (receipt,))
        return cur.rowcount == 1


def release(receipt: str, delay: float = 5) -> None:
    with _connect() as conn:
        conn.execute("UPDATE deliveries SET state='pending', available_at=?, receipt='' "
                     "WHERE receipt=? AND state='processing'", (time.time() + delay, receipt))


def pending_count(platform: str, corpid: str, agent_id: str, recipient: str) -> int:
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM deliveries WHERE platform=? AND corpid=? "
                            "AND agent_id=? AND recipient=? AND state!='done'",
                            (platform, corpid, agent_id, recipient)).fetchone()[0]
