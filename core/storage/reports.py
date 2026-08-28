"""报告仓储：upsert 保存、按平台查询、SSE 增量游标。"""
from __future__ import annotations

from core.models import ReportData


class ReportRepo:
    """依赖 StorageBase 提供的 self._connect / self._lock。"""

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
