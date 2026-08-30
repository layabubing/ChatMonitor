"""提醒仓储：入库去重、分页查询、批量已读、SSE 增量游标。"""
from __future__ import annotations

from core.models import ImportantItem


class AlertRepo:
    """依赖 StorageBase 提供的 self._connect / self._lock。"""

    def add_alert(self, item: ImportantItem) -> int:
        """插入提醒（同一平台+msg_id 去重）；返回 1=新增 0=已存在。"""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO alerts "
                "(platform, msg_id, content, reason, suggestion, priority, sender, group_name, ts) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (item.platform, item.msg_id, item.content, item.reason, item.suggestion,
                 item.priority, item.sender, item.group_name, int(item.ts)),
            )
            conn.commit()
            return cur.rowcount

    def query_alerts(self, platform: str = "", unread_only: bool = False,
                     page: int = 1, page_size: int = 50) -> dict:
        where, params = [], []
        if platform:
            where.append("platform = ?")
            params.append(platform)
        if unread_only:
            where.append("is_read = 0")
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self._connect() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM alerts {clause}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM alerts {clause} ORDER BY ts DESC LIMIT ? OFFSET ?",
                [*params, page_size, (page - 1) * page_size],
            ).fetchall()
        return {"total": total, "page": page, "page_size": page_size, "items": [dict(r) for r in rows]}

    def mark_alerts_read(self, ids: list[int] | None = None, platform: str = "") -> int:
        with self._lock, self._connect() as conn:
            if ids:
                ph = ",".join("?" * len(ids))
                cur = conn.execute(f"UPDATE alerts SET is_read=1 WHERE id IN ({ph})", ids)
            else:
                where = "platform=?" if platform else "1=1"
                params = [platform] if platform else []
                cur = conn.execute(f"UPDATE alerts SET is_read=1 WHERE {where}", params)
            conn.commit()
            return cur.rowcount

    def max_alert_id(self, platform: str) -> int:
        """该平台最新提醒 id（无提醒返回 0）。"""
        with self._connect() as conn:
            row = conn.execute("SELECT MAX(id) FROM alerts WHERE platform=?", (platform,)).fetchone()
            return row[0] or 0

    def get_alert(self, alert_id: int) -> dict | None:
        """按 id 取提醒（不存在返回 None）——SSE 事件载荷摘要。"""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM alerts WHERE id=?", (int(alert_id),)).fetchone()
        return dict(row) if row else None
