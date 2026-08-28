"""文件库仓储：媒体文件记录、AI 识别结果、分页/过滤查询、重要标记。"""
from __future__ import annotations


class FileRepo:
    """依赖 StorageBase 提供的 self._connect / self._lock。"""

    def add_file(self, platform: str, msg_id: str, local_path: str, orig_name: str,
                 ftype: str, ext: str, size: int, ts: int) -> int:
        """记录一个已保存的媒体文件；返回 1=新增 0=已存在。"""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO files (platform, msg_id, local_path, orig_name, ftype, ext, size, ts) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (platform, msg_id, local_path, orig_name, ftype, ext, size, int(ts)),
            )
            conn.commit()
            return cur.rowcount

    def update_file_ai(self, platform: str, local_path: str, important: int,
                       ai_desc: str, category: str) -> bool:
        """更新文件的 AI 识别结果（重要性标记、描述、分类）。"""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE files SET important=?, ai_desc=?, category=? WHERE platform=? AND local_path=?",
                (important, ai_desc, category, platform, local_path),
            )
            conn.commit()
            return cur.rowcount > 0

    def query_files(self, platform: str = "", important_only: bool = False,
                    category: str = "", q: str = "",
                    page: int = 1, page_size: int = 50) -> dict:
        """分页查询文件库。"""
        where, params = [], []
        if platform:
            where.append("platform = ?")
            params.append(platform)
        if important_only:
            where.append("important = 1")
        if category:
            where.append("category = ?")
            params.append(category)
        if q:
            where.append("(orig_name LIKE ? OR ai_desc LIKE ?)")
            params += [f"%{q}%", f"%{q}%"]
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self._connect() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM files {clause}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM files {clause} ORDER BY ts DESC LIMIT ? OFFSET ?",
                [*params, page_size, (page - 1) * page_size],
            ).fetchall()
        return {"total": total, "page": page, "page_size": page_size, "items": [dict(r) for r in rows]}

    def file_categories(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT DISTINCT category FROM files WHERE category!='' ORDER BY category").fetchall()
        return [r[0] for r in rows]

    def get_file(self, fid: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM files WHERE id=?", (fid,)).fetchone()
            return dict(row) if row else None

    def set_file_important(self, fid: int, important: int) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("UPDATE files SET important=? WHERE id=?", (important, fid))
            conn.commit()
            return cur.rowcount > 0

    def max_file_id(self, platform: str) -> int:
        """该平台最新文件 id（无文件返回 0）。"""
        with self._connect() as conn:
            row = conn.execute("SELECT MAX(id) FROM files WHERE platform=?", (platform,)).fetchone()
            return row[0] or 0
