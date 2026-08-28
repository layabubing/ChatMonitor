"""
SQLite 存储层：Storage 门面 = 连接基类 + 各表仓储 Mixin 的组合。
对外 API 与重构前完全一致（from core.storage import Storage 不变）。

按表拆分的仓储：
- base.StorageBase     连接/schema/跨表概览
- messages.MessageRepo 消息
- alerts.AlertRepo     提醒
- reports.ReportRepo   日报
- files.FileRepo       文件库
- cursors.CursorRepo   增量游标
"""
from __future__ import annotations

from core.storage.alerts import AlertRepo
from core.storage.base import StorageBase
from core.storage.cursors import CursorRepo
from core.storage.files import FileRepo
from core.storage.messages import MessageRepo
from core.storage.reports import ReportRepo


class Storage(StorageBase, MessageRepo, AlertRepo, ReportRepo, FileRepo, CursorRepo):
    """多表存储门面：方法由各表仓储 Mixin 提供，共享同一连接管理与写锁。"""


__all__ = ["Storage", "StorageBase"]
