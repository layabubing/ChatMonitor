"""
平台适配器抽象基类 + 工厂
每个平台一个独立进程，实现本接口即可接入流水线
"""
from __future__ import annotations

import abc
import queue
import threading
import time
from collections.abc import Iterator

from core.models import ChatMessage


class PlatformAdapter(abc.ABC):
    """平台适配器统一接口"""

    name: str = ""          # qq / dingtalk

    def __init__(self, config: dict, username: str = ""):
        self.config = config
        self.username = username   # 多租户：所属用户（空=全局）
        self._running = False
        self._queue: queue.Queue[ChatMessage | None] = queue.Queue()
        self._thread: threading.Thread | None = None

    # ── 生命周期 ──
    @abc.abstractmethod
    def _connect(self) -> None:
        """建立连接/初始化（在子线程中调用）"""

    @abc.abstractmethod
    def _run_loop(self) -> None:
        """消息获取主循环：持续向 self._queue.put(ChatMessage)"""

    def start(self) -> None:
        """启动适配器（后台线程）"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True, name=f"{self.name}-adapter")
        self._thread.start()

    def _worker(self) -> None:
        """适配器守护线程：异常后自动重启（避免僵尸 worker 静默失联）"""
        while self._running:
            try:
                self._connect()
                self._run_loop()
            except Exception as e:  # noqa: BLE001
                print(f"[{self.name}] 适配器异常: {e}")
            if not self._running:
                break   # stop() 正常退出
            print(f"[{self.name}] 适配器异常退出，5 秒后自动重启…")
            time.sleep(5)
        print(f"[{self.name}] 适配器已停止")

    def stop(self) -> None:
        """停止适配器（放哨兵消息唤醒主循环）"""
        self._running = False
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=3)

    # ── 消息消费 ──
    def iter_messages(self, timeout: float = 1.0) -> Iterator[ChatMessage]:
        """产出新消息；超时返回空；哨兵 None 表示适配器已停止"""
        try:
            item = self._queue.get(timeout=timeout)
            if item is not None:
                yield item
        except queue.Empty:
            return

    def _emit(self, msg: ChatMessage) -> None:
        """子线程调用：投递一条消息"""
        self._queue.put(msg)

    # ── 状态 ──
    def health(self) -> dict:
        return {"platform": self.name, "running": self._running}

    @staticmethod
    def create(platform: str, config: dict, username: str = "") -> PlatformAdapter:
        """工厂：创建平台适配器实例（username 指定时为多租户用户实例）"""
        if platform == "qq":
            from platforms.qq import QQAdapter
            return QQAdapter(config, username)
        if platform == "dingtalk":
            from platforms.dingtalk import DingTalkAdapter
            return DingTalkAdapter(config, username)
        raise ValueError(f"未知平台: {platform}")
