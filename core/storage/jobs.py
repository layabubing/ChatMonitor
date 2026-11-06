"""Persistent AI work. Jobs are created in the message ingestion transaction."""
from __future__ import annotations

import json
import time
import uuid


def enqueue_jobs(conn, message) -> None:
    jobs = [(message.msg_id, "importance", "")]
    jobs.extend((message.msg_id, "media", path) for path in message.media_urls or []
                if isinstance(path, str) and path.startswith(("media/", "users/")))
    conn.executemany("INSERT OR IGNORE INTO analysis_jobs(msg_id, kind, target) VALUES (?,?,?)", jobs)


class AnalysisRepo:
    def claim_analysis(self, platform: str, lease_seconds: float = 300) -> dict | None:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT j.*, m.* FROM analysis_jobs j JOIN messages m USING(msg_id) "
                "WHERE m.platform=? AND j.state!='done' AND j.available_at<=? "
                "ORDER BY j.available_at, m.ts, j.msg_id, j.kind LIMIT 1", (platform, now),
            ).fetchone()
            if row is None:
                return None
            job = dict(row)
            receipt = uuid.uuid4().hex
            conn.execute("UPDATE analysis_jobs SET state='running', attempts=attempts+1, "
                         "available_at=?, receipt=? WHERE msg_id=? AND kind=? AND target=?",
                         (now + lease_seconds, receipt, job['msg_id'], job['kind'], job['target']))
            job['receipt'] = receipt
            job['media_urls'] = json.loads(job['media_urls'])
            return job

    def finish_analysis(self, receipt: str, error: str = "") -> None:
        with self._lock, self._connect() as conn:
            if error:
                row = conn.execute("SELECT attempts FROM analysis_jobs WHERE receipt=?", (receipt,)).fetchone()
                if row is None:
                    return
                delay = min(3600, 30 * 2 ** min(row['attempts'] - 1, 7))
                conn.execute("UPDATE analysis_jobs SET state='failed', available_at=?, "
                             "last_error=?, receipt='' WHERE receipt=?",
                             (time.time() + delay, error[:120], receipt))
            else:
                conn.execute("UPDATE analysis_jobs SET state='done', last_error='', receipt='' WHERE receipt=?",
                             (receipt,))
            conn.commit()

    def reset_failed_analysis(self, platform: str) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.execute("UPDATE analysis_jobs SET state='pending', available_at=0 "
                               "WHERE state='failed' AND msg_id IN "
                               "(SELECT msg_id FROM messages WHERE platform=?)", (platform,))
            conn.commit()
            return cur.rowcount

    def analysis_status(self, platform: str = "", start: int | None = None, end: int | None = None) -> dict:
        result = dict.fromkeys(('pending', 'running', 'failed', 'done'), 0)
        where, params = [], []
        if platform:
            where.append('m.platform=?')
            params.append(platform)
        if start is not None:
            where.append('m.ts>=?')
            params.append(start)
        if end is not None:
            where.append('m.ts<?')
            params.append(end)
        clause = ' WHERE ' + ' AND '.join(where) if where else ''
        with self._connect() as conn:
            for row in conn.execute("SELECT j.state, COUNT(*) AS n FROM analysis_jobs j "
                                    "JOIN messages m USING(msg_id)" + clause + " GROUP BY j.state", params):
                result[row['state']] = row['n']
        return result

    def reschedule_importance(self, msg_ids: list[str]) -> None:
        """Explicit keyword rescan can revisit completed negative judgments."""
        with self._lock, self._connect() as conn:
            for msg_id in msg_ids:
                conn.execute("INSERT OR IGNORE INTO analysis_jobs(msg_id, kind) VALUES (?, 'importance')",
                             (msg_id,))
                conn.execute("UPDATE analysis_jobs SET state='pending', available_at=0 "
                             "WHERE msg_id=? AND kind='importance' AND state!='running'", (msg_id,))
            conn.commit()
