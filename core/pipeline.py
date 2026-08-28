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
    def process_batch(self, msgs: list[ChatMessage]) -> int:
        """处理一批消息：入库去重，命中关键词的送 AI 确认，重要则提醒"""
        if not msgs or self.is_paused():
            return 0
        added_ids = self.storage.insert_messages(msgs)
        if not added_ids:
            return 0
        added_set = set(added_ids)
        # 只对【本次新增】的消息做判定，避免重复提醒
        new_msgs = [m for m in msgs if m.msg_id in added_set and m.content]
        # 媒体处理：保存的文件入库 + AI 识别重要文件
        self._process_media(msgs, added_set)
        candidates = [m for m in new_msgs if self._match(m.content)]
        if candidates:
            try:
                loop = asyncio.new_event_loop()
                try:
                    items = loop.run_until_complete(
                        analyzer.confirm_importance(self.config, candidates))
                finally:
                    loop.close()
            except Exception as e:  # noqa: BLE001
                print(f"[pipeline] AI 确认失败: {e}")
                items = []
            for it in items:
                if self.storage.add_alert(it):
                    print(f"[{self.platform}] ⚠ 重要提醒 [{it.priority}]: {it.content[:40]} | 建议: {it.suggestion[:40]}")
                    self._push_serverchan(it)
        return len(added_ids)

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
    def _process_media(self, msgs: list[ChatMessage], added_set: set) -> None:
        for m in msgs:
            if m.msg_id not in added_set:
                continue
            for idx, path in enumerate(m.media_urls or []):
                if not isinstance(path, str):
                    continue
                # 多租户：路径可能是 media/ 或 users/{username}/media/
                if not (path.startswith("media/") or path.startswith("users/")):
                    continue
                try:
                    self._handle_saved_media(m, path, idx)
                except Exception as e:  # noqa: BLE001
                    print(f"[pipeline] 媒体处理失败: {e}")

    def _handle_saved_media(self, m: ChatMessage, path: str, idx: int) -> None:
        abs_path = DATA_DIR / path
        if not abs_path.exists():
            return
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        ftype = media.guess_type(ext, path, abs_path.name)
        orig_name = abs_path.name
        size = abs_path.stat().st_size
        added = self.storage.add_file(self.platform, m.msg_id, path, orig_name,
                                      ftype, ext, size, m.ts)
        if not added:
            return
        # AI 识别：图片用视觉模型，其他用文本模型
        try:
            loop = asyncio.new_event_loop()
            try:
                if ftype == "image":
                    info = loop.run_until_complete(
                        analyzer.analyze_image(self.config, str(abs_path), m.content))
                else:
                    info = loop.run_until_complete(
                        analyzer.analyze_file(self.config, orig_name, m.content))
            finally:
                loop.close()
        except Exception as e:  # noqa: BLE001
            print(f"[pipeline] 文件 AI 识别失败: {e}")
            return
        if not info:
            return
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
        """生成当日报告（由 scheduler 或命令触发）"""
        from core.reporter import generate_report
        return generate_report(self.storage, self.config, self.platform, date_str, self.username)

    # ── 补判定：重载关键词后对今日未提醒消息重新扫描 ──
    def rescan_today(self) -> int:
        """重新扫描当日已入库但未产生提醒的消息，补做关键词+AI 判定；返回新增提醒数"""
        import datetime
        today_start = int(datetime.datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        res = self.storage.query_messages(self.platform, page=1, page_size=2000)
        msgs_today = [m for m in res["items"] if m["ts"] >= today_start]
        if not msgs_today:
            return 0
        alerts = self.storage.query_alerts(platform=self.platform, page=1, page_size=500)["items"]
        alerted_ids = {a["msg_id"] for a in alerts}
        candidates = [
            ChatMessage(msg_id=m["msg_id"], platform=self.platform, group_id=m["group_id"],
                        group_name=m["group_name"], sender=m["sender"], content=m["content"],
                        msg_type=m["msg_type"], ts=m["ts"])
            for m in msgs_today
            if m["msg_id"] not in alerted_ids and m["content"] and self._match(m["content"])
        ]
        if not candidates:
            return 0
        try:
            loop = asyncio.new_event_loop()
            try:
                items = loop.run_until_complete(
                    analyzer.confirm_importance(self.config, candidates))
            finally:
                loop.close()
        except Exception as e:  # noqa: BLE001
            print(f"[pipeline] 补判定 AI 调用失败: {e}")
            return 0
        n = 0
        for it in items:
            if self.storage.add_alert(it):
                n += 1
                print(f"[{self.platform}] ⚠ 补判定重要提醒 [{it.priority}]: {it.content[:40]} | 建议: {it.suggestion[:40]}")
                self._push_serverchan(it)
        print(f"[{self.platform}] 补判定完成，新增提醒 {n} 条")
        return n
