"""Calendar day boundaries in the configured report timezone (local by default)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def day_bounds(date_str: str, timezone: str = "") -> tuple[int, int]:
    day = date.fromisoformat(date_str)
    if day.isoformat() != date_str:
        raise ValueError("日期必须使用 YYYY-MM-DD")
    tz = ZoneInfo(timezone) if timezone else None
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def today(timezone: str = "") -> str:
    return datetime.now(ZoneInfo(timezone) if timezone else None).date().isoformat()
