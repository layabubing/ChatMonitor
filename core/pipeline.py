"""
消息处理流水线：入库去重 → 关键词过滤 → AI 确认 → 重要提醒入库+推送
"""
from __future__ import annotations

import asyncio
import threading

import httpx

from config import DATA_DIR
from core import accounts, analyzer, keywords, media

# ── 向后兼容 re-export（既有调用方仍可 from core.pipeline import ...） ──
from core.keywords import (  # noqa: F401
    get_keyword_categories,
    load_keywords,
    save_keywords,
)
from core.models import ChatMessage, ImportantItem
from core.storage import Storage


class Pipeline:
    """单平台消息流水线（worker 进程内使用；username 指定时为用户级多租户实例）"""

    def __init__(self, storage: Storage, config: dict, platform: str, username: str = ""):
        self.storage = storage
        self.config = config
        self.platform = platform
        self.username = username
        self._paused = False
        self._lock = threading.Lock()
        self._analysis_lock = threading.Lock()
        self._report_lock = threading.Lock()
        # 用户级实例使用用户自己的关键词库（多租户）
        self._user_words: list[str] = []
        if username:
            self._user_words = accounts.flatten(accounts.get_user_keywords(username))
        keywords.load_keywords()

    def _match(self, text: str) -> bool:
        """关键词匹配：用户级实例用用户词库（为空则回退全局）；全局实例用全局词库"""
        if not text:
            return False
        if self.username and self._user_words:
            return keywords.match(text, self._user_words)
        return keywords.match(text)

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False

    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    # ── 主入口 ──
    def process_batch(self, msgs: list[ChatMessage], analyze: bool = True) -> int:
        """Persist messages AND AI work atomically before acknowledging delivery.

        Workers pass analyze=False; the scheduler processes persistent jobs outside
        ingestion. The default keeps the synchronous API used by local tools.
        """
        if not msgs:
            return 0
        added_ids = self.storage.insert_messages(msgs, enqueue_analysis=True)
        if analyze:
            self.retry_analysis(limit=max(20, len(msgs) * 2))
        return len(added_ids)

    def retry_analysis(self, limit: int = 20) -> int:
        """Run due/expired jobs, retaining failures with bounded exponential backoff."""
        if self.is_paused() or not self._analysis_lock.acquire(blocking=False):
            return 0
        completed = 0
        try:
            for _ in range(limit):
                job = self.storage.claim_analysis(self.platform)
                if job is None:
                    break
                message = ChatMessage(**{key: job[key] for key in (
                    'msg_id', 'platform', 'group_id', 'group_name', 'sender', 'content',
                    'msg_type', 'media_urls', 'ts')})
                try:
                    if job['kind'] == 'media':
                        self._handle_saved_media(message, job['target'], 0)
                    elif self._match(message.content):
                        items = asyncio.run(analyzer.confirm_importance(self.config, [message]))
                        for item in items:
                            if self.storage.add_alert(item):
                                self._push_serverchan(item)
                    self.storage.finish_analysis(job['receipt'])
                    completed += 1
                except Exception as exc:  # noqa: BLE001
                    # Only our controlled error messages may be persisted. Raw
                    # network exceptions can contain URLs, tokens or message data.
                    error = str(exc) if isinstance(exc, analyzer.AnalysisError) else type(exc).__name__
                    self.storage.finish_analysis(job['receipt'], error=error)
                    print(f"[{self.platform}] AI 分析待补跑 ({job['kind']}): {error}")
        finally:
            self._analysis_lock.release()
        return completed

    # ── 可选推送（Server酱） ──
    def _push_serverchan(self, item: ImportantItem) -> None:
        key = self.config.get("SERVERCHAN_KEY", "")
        if not key:
            return
        try:
            httpx.post(
                f"https://sctapi.ftqq.com/{key}.send",
                data={"title": f"[{self.platform.upper()}] 重要消息提醒",
                      "desp": f"优先级: {item.priority}\n来源: {item.group_name} / {item.sender}\n内容: {item.content}\n\n建议: {item.suggestion}"},
                timeout=10,
            )
        except Exception as e:  # noqa: BLE001
            print(f"[pipeline] Server酱推送失败: {e}")

    # ── 媒体处理：本地保存的文件入库 + AI 识别重要文件 ──
    def _handle_saved_media(self, m: ChatMessage, path: str, idx: int) -> None:
        abs_path = DATA_DIR / path
        if not abs_path.exists():
            raise analyzer.AnalysisError("待识别媒体不存在")
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        ftype = media.guess_type(ext, path, abs_path.name)
        orig_name = abs_path.name
        size = abs_path.stat().st_size
        self.storage.add_file(self.platform, m.msg_id, path, orig_name,
                              ftype, ext, size, m.ts)
        if ftype == "image":
            info = asyncio.run(analyzer.analyze_image(self.config, str(abs_path), m.content))
        else:
            info = asyncio.run(analyzer.analyze_file(self.config, orig_name, m.content))
        if not info or type(info.get('important')) is not bool:
            raise analyzer.AnalysisError("文件分析无有效结果")
        important = 1 if info.get("important") else 0
        self.storage.update_file_ai(self.platform, path, important,
                                    info.get("desc", ""), info.get("category", "其他"))
        print(f"[{self.platform}] 文件识别: {orig_name} 重要={important} 类别={info.get('category')} | {info.get('desc', '')[:40]}")
        if important:
            it = ImportantItem(
                platform=self.platform, msg_id=m.msg_id,
                content=f"[重要文件] {orig_name}（{info.get('category', '其他')}）: {info.get('desc', '')[:80]}",
                reason="AI 识别为重要资料", suggestion="请查看该文件并归档处理",
                priority="medium", sender=m.sender, group_name=m.group_name, ts=m.ts)
            if self.storage.add_alert(it):
                print(f"[{self.platform}] ⚠ 重要文件提醒: {orig_name}")
                self._push_serverchan(it)

    # ── 日报 ──
    def build_daily_report(self, date_str: str | None = None):
        """Persist a report request before attempting it (scheduler or command)."""
        from core.dates import day_bounds, today
        date_str = date_str or today(self.config.get('REPORT_TIMEZONE', ''))
        day_bounds(date_str, self.config.get('REPORT_TIMEZONE', ''))
        self.storage.request_report(self.platform, date_str)
        return self.retry_reports(date_str)

    def retry_reports(self, date_str: str | None = None):
        """Retry one due report, including AI failures and interrupted generation."""
        from core.reporter import generate_report
        if self.is_paused() or not self._report_lock.acquire(blocking=False):
            return None
        try:
            task = self.storage.claim_report(self.platform, date_str)
            if task is None:
                return None
            try:
                report = generate_report(self.storage, self.config, self.platform, task['date'], self.username)
            except Exception as exc:  # noqa: BLE001
                error = str(exc) if isinstance(exc, analyzer.AnalysisError) else type(exc).__name__
                self.storage.finish_report(task['receipt'], error)
                print(f"[{self.platform}] 日报待补跑 ({task['date']}): {error}")
                return None
            self.storage.finish_report(task['receipt'])
            return report
        finally:
            self._report_lock.release()

    # ── 补判定：重载关键词后对今日未提醒消息重新扫描 ──
    def rescan_today(self) -> int:
        """Persist a complete-day keyword rescan; failures use the same retry queue."""
        from core.dates import day_bounds, today
        timezone = self.config.get('REPORT_TIMEZONE', '')
        start, end = day_bounds(today(timezone), timezone)
        messages, alerts = self.storage.report_inputs(self.platform, start, end)
        alerted_ids = {alert['msg_id'] for alert in alerts}
        ids = [message['msg_id'] for message in messages
               if message['msg_id'] not in alerted_ids and self._match(message['content'])]
        self.storage.reschedule_importance(ids)
        print(f"[{self.platform}] 已安排补判定 {len(ids)} 条消息")
        return len(ids)
