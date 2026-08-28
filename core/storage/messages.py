"""消息仓储：入库去重、分页/搜索、当日统计、群列表、SSE 增量游标。"""
from __future__ import annotations

import datetime
import json

from core.models import ChatMessage


class MessageRepo:
    """依赖 StorageBase 提供的 self._connect / self._lock。"""

    def insert_messages(self, msgs: list[ChatMessage]) -> list[str]:
        """批量插入，按 msg_id 去重；返回本次【新增】的 msg_id 列表。"""
        if not msgs:
            return []
        added_ids: list[str] = []
        import sqlite3
        with self._lock, self._connect() as conn:
            for m in msgs:
                try:
                    cur = conn.execute(
                        "INSERT OR IGNORE INTO messages "
                        "(msg_id, platform, group_id, group_name, sender, content, msg_type, media_urls, ts) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (m.msg_id, m.platform, m.group_id, m.group_name, m.sender, m.content,
                         m.msg_type, json.dumps(m.media_urls, ensure_ascii=False), int(m.ts)),
                    )
                    if cur.rowcount:
                        added_ids.append(m.msg_id)
                except sqlite3.IntegrityError:
                    continue
            conn.commit()
        return added_ids

    def query_messages(self, platform: str, group: str = "", q: str = "",
                       page: int = 1, page_size: int = 50) -> dict:
        """分页查询消息（media_urls 自动解析为列表）。"""
        where = ["platform = ?"]
        params: list = [platform]
        if group:
            where.append("group_name = ?")
            params.append(group)
        if q:
            where.append("(content LIKE ? OR sender LIKE ?)")
            params += [f"%{q}%", f"%{q}%"]
        with self._connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM messages WHERE {' AND '.join(where)}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM messages WHERE {' AND '.join(where)} ORDER BY ts DESC LIMIT ? OFFSET ?",
                [*params, page_size, (page - 1) * page_size],
            ).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            try:
                d["media_urls"] = json.loads(d.get("media_urls") or "[]")
            except Exception:  # noqa: BLE001
                d["media_urls"] = []
            items.append(d)
        return {"total": total, "page": page, "page_size": page_size, "items": items}

    def count_messages_today(self, platform: str) -> int:
        """当日消息数（本地时区）。"""
        start = int(datetime.datetime.now().replace(hour=0, minute=0, second=0).timestamp() * 1000)
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM messages WHERE platform=? AND ts>=?", (platform, start)
            ).fetchone()[0]

    def distinct_groups(self, platform: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT group_name FROM messages WHERE platform=? AND group_name!='' ORDER BY group_name",
                (platform,),
            ).fetchall()
        return [r[0] for r in rows]

    def max_msg_ts(self, platform: str) -> int:
        """该平台最新消息时间戳（无消息返回 0）——SSE 增量游标。"""
        with self._connect() as conn:
            row = conn.execute("SELECT MAX(ts) FROM messages WHERE platform=?", (platform,)).fetchone()
            return row[0] or 0
