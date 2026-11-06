"""报告仓储：upsert 保存、按平台查询、SSE 增量游标。"""
from __future__ import annotations

import json
import time
import uuid

from core.models import ReportData


class ReportPendingError(RuntimeError):
    """The input snapshot still includes unfinished message analysis."""


class ReportRepo:
    """依赖 StorageBase 提供的 self._connect / self._lock。"""

    def request_report(self, platform: str, date: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("INSERT INTO report_tasks(platform, date) VALUES (?,?) "
                         "ON CONFLICT(platform, date) DO UPDATE SET state='pending', available_at=0 "
                         "WHERE report_tasks.state!='running'", (platform, date))
            conn.commit()

    def claim_report(self, platform: str, date: str | None = None) -> dict | None:
        with self._lock, self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            condition, params = (' AND date=?', [date]) if date else ('', [])
            row = conn.execute("SELECT * FROM report_tasks WHERE platform=? AND state!='done' "
                               "AND available_at<=?" + condition + " ORDER BY date LIMIT 1",
                               [platform, time.time(), *params]).fetchone()
            if row is None:
                return None
            receipt = uuid.uuid4().hex
            conn.execute("UPDATE report_tasks SET state='running', attempts=attempts+1, "
                         "available_at=?, receipt=? WHERE platform=? AND date=?",
                         (time.time() + 3600, receipt, platform, row['date']))
            return {**dict(row), 'receipt': receipt}

    def finish_report(self, receipt: str, error: str = '') -> None:
        with self._lock, self._connect() as conn:
            row = conn.execute('SELECT attempts FROM report_tasks WHERE receipt=?', (receipt,)).fetchone()
            if row is None:
                return
            delay = min(3600, 30 * 2 ** min(row['attempts'] - 1, 7))
            conn.execute("UPDATE report_tasks SET state=?, available_at=?, last_error=?, receipt='' "
                         "WHERE receipt=?", ('failed' if error else 'done', time.time() + delay,
                                             error[:120], receipt))
            conn.commit()

    def report_task_status(self, platform: str) -> dict:
        with self._connect() as conn:
            return {row['state']: row['n'] for row in conn.execute(
                'SELECT state, COUNT(*) AS n FROM report_tasks WHERE platform=? GROUP BY state', (platform,))}

    def reset_failed_reports(self, platform: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE report_tasks SET state='pending', available_at=0 "
                         "WHERE platform=? AND state='failed'", (platform,))
            conn.commit()

    def report_inputs(self, platform: str, start: int, end: int,
                      require_analyzed: bool = False) -> tuple[list[dict], list[dict]]:
        """Read the complete half-open date range from one consistent snapshot."""
        with self._connect() as conn:
            conn.execute("BEGIN")
            if require_analyzed and conn.execute(
                "SELECT 1 FROM analysis_jobs j JOIN messages m USING(msg_id) "
                "WHERE m.platform=? AND m.ts>=? AND m.ts<? AND j.state!='done' LIMIT 1",
                (platform, start, end),
            ).fetchone():
                raise ReportPendingError("当日消息 AI 判定尚未完成，日报待补跑")
            messages = [dict(row) for row in conn.execute(
                "SELECT * FROM messages WHERE platform=? AND ts>=? AND ts<? ORDER BY ts, msg_id",
                (platform, start, end))]
            alerts = [dict(row) for row in conn.execute(
                "SELECT * FROM alerts WHERE platform=? AND ts>=? AND ts<? ORDER BY ts, id",
                (platform, start, end))]
        for message in messages:
            message['media_urls'] = json.loads(message['media_urls'] or '[]')
        return messages, alerts

    def save_report(self, report: ReportData) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO reports
                   (platform, date, summary, docx_path, html_path, msg_count, important_count, created_at)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(platform, date) DO UPDATE SET
                     summary=excluded.summary, docx_path=excluded.docx_path, html_path=excluded.html_path,
                     msg_count=excluded.msg_count, important_count=excluded.important_count,
                     created_at=excluded.created_at""",
                (report.platform, report.date, report.summary, report.docx_path, report.html_path,
                 report.msg_count, report.important_count, int(report.created_at)),
            )
            conn.commit()

    def query_reports(self, platform: str = "", limit: int = 30) -> list[dict]:
        where, params = [], []
        if platform:
            where.append("platform=?")
            params.append(platform)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM reports {clause} ORDER BY date DESC LIMIT ?", [*params, limit]
            ).fetchall()
        return [dict(r) for r in rows]

    def max_report_id(self, platform: str) -> int:
        """该平台最新报告 id（无报告返回 0）。"""
        with self._connect() as conn:
            row = conn.execute("SELECT MAX(id) FROM reports WHERE platform=?", (platform,)).fetchone()
            return row[0] or 0
