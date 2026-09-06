"""
数据模型定义
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field


def _now_ts() -> float:
    return time.time() * 1000  # 统一毫秒


PRIORITIES = ("high", "medium", "low")


def normalize_priority(value) -> str:
    """优先级白名单：非法值回退 medium（AI 输出不可信，防止注入恶意内容入库）。"""
    v = str(value or "").strip().lower()
    return v if v in PRIORITIES else "medium"


@dataclass
class ChatMessage:
    """标准化聊天消息"""
    msg_id: str                    # 平台消息唯一 ID（去重键）
    platform: str                  # qq / dingtalk
    group_id: str = ""
    group_name: str = ""
    sender: str = ""
    content: str = ""
    msg_type: str = "text"         # text / image / video / file / other
    media_urls: list = field(default_factory=list)   # 图片/文件 URL（多模态分析用）
    ts: float = field(default_factory=_now_ts)       # 毫秒时间戳

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ts"] = int(d["ts"])
        return d


@dataclass
class ImportantItem:
    """重要提醒条目"""
    platform: str
    msg_id: str = ""
    content: str = ""
    reason: str = ""
    suggestion: str = ""           # 执行建议
    priority: str = "medium"       # high / medium / low
    sender: str = ""
    group_name: str = ""
    ts: float = field(default_factory=_now_ts)
    is_read: int = 0

    def __post_init__(self) -> None:
        self.priority = normalize_priority(self.priority)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ts"] = int(d["ts"])
        return d


@dataclass
class ReportData:
    """日报记录"""
    platform: str
    date: str                      # YYYY-MM-DD
    summary: str = ""
    docx_path: str = ""
    html_path: str = ""
    msg_count: int = 0
    important_count: int = 0
    created_at: float = field(default_factory=_now_ts)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_at"] = int(d["created_at"])
        return d


def ts_to_str(ts: float, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """时间戳转字符串（本地时区）"""
    import datetime
    return datetime.datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts).strftime(fmt)
