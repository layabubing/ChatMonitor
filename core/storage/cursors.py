"""游标仓储：平台增量拉取游标（跨重启续拉）。"""
from __future__ import annotations


class CursorRepo:
    """依赖 StorageBase 提供的 self._connect / self._lock。"""

    def get_cursor(self, platform: str, default: str = "") -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM cursor WHERE platform=?", (platform,)).fetchone()
            return row["value"] if row else default

    def set_cursor(self, platform: str, value: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO cursor (platform, value) VALUES (?,?) "
                "ON CONFLICT(platform) DO UPDATE SET value=excluded.value",
                (platform, value),
            )
            conn.commit()
