"""
企业微信适配器（回调模式：web 收回调 → 收件箱 inbox → 本适配器轮询消费）
- 消息来源: 应用消息回调 / 群机器人回调（web 进程经 core.inbox 转交）
- 媒体: 图片/语音/文件通过 cgi-bin/media/get 下载（需应用 secret 换取 access_token）
- 多租户: 按 corpid + agent_id 匹配归属实例（同一回调 URL 服务多个绑定）
"""
from __future__ import annotations

import time

import httpx

from core import inbox
from core.adapter import PlatformAdapter
from core.models import ChatMessage

_TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
_MEDIA_URL = "https://qyapi.weixin.qq.com/cgi-bin/media/get"

_EXT_MAP = {
    "image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png",
    "image/gif": "gif", "image/webp": "webp", "image/bmp": "bmp",
    "audio/amr": "amr", "audio/mpeg": "mp3", "audio/mp3": "mp3",
    "audio/x-wav": "wav", "audio/ogg": "ogg", "audio/silk": "silk",
    "video/mp4": "mp4", "application/pdf": "pdf",
}


class WorkWechatAdapter(PlatformAdapter):
    name = "workwechat"

    def __init__(self, config: dict, username: str = ""):
        super().__init__(config, username)
        self._corp_id = config.get("WORKWECHAT_CORP_ID", "")
        self._agent_id = str(config.get("WORKWECHAT_AGENT_ID", "") or "")
        self._group_filter: set[str] = {
            g for g in (config.get("WORKWECHAT_CHAT_IDS") or "").split(",") if g.strip()}
        self._token = ""
        self._token_expire = 0.0

    # ── 鉴权 ──
    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expire - 60:
            return self._token
        resp = httpx.get(_TOKEN_URL, params={
            "corpid": self._corp_id,
            "corpsecret": self.config.get("WORKWECHAT_SECRET", ""),
        }, timeout=15)
        data = resp.json()
        if data.get("errcode", 0) != 0 or not data.get("access_token"):
            raise RuntimeError(f"企微 access_token 获取失败: {data}")
        self._token = data["access_token"]
        self._token_expire = time.time() + int(data.get("expires_in", 7200))
        return self._token

    # ── 连接与主循环 ──
    def _connect(self) -> None:
        pass  # 轮询模式无需常驻连接

    def _run_loop(self) -> None:
        # 多租户隔离：每个实例只消费自己 corpid 子目录（web 回调按 corpid 分目录写入）
        scope = self._corp_id or ""
        while self._running:
            try:
                for raw in inbox.pop_messages("workwechat", scope=scope):
                    msg = self._to_chatmessage(raw)
                    if msg:
                        self._emit(msg)
            except Exception as e:  # noqa: BLE001
                print(f"[workwechat] 收件箱消费异常: {e}")
            for _ in range(10):   # 2 秒轮询（可被 stop 打断）
                if not self._running:
                    break
                time.sleep(0.2)

    # ── 消息转换 ──
    def _to_chatmessage(self, raw: dict) -> ChatMessage | None:
        # 路由匹配：corpid / agent_id 归属本实例（不同绑定各自消费）
        if self._corp_id and raw.get("corpid") and raw.get("corpid") != self._corp_id:
            return None
        if self._agent_id and raw.get("agent_id") and str(raw.get("agent_id")) != self._agent_id:
            return None
        chat_id = raw.get("chat_id", "")
        if not chat_id:
            return None
        if self._group_filter and chat_id not in self._group_filter:
            return None
        media_urls: list[str] = []
        for mid in raw.get("media_ids") or []:
            local = self._download_media(mid)
            media_urls.append(local or mid)   # 下载失败保留 media_id 占位
        content = raw.get("content", "") or ""
        # 语音且已下载成功（本地路径含 "/"，占位 media_id 无）→ 尝试转写
        if raw.get("msg_type") == "voice" and media_urls and "/" in media_urls[0]:
            text = self._transcribe(media_urls[0])
            content = f"🎤 [语音] 转写：{text}" if text else "[语音]（已保存，转写失败）"
        return ChatMessage(
            msg_id=raw.get("msg_id", ""),
            platform="workwechat", group_id=chat_id, group_name=raw.get("group_name") or chat_id[-8:],
            sender=raw.get("sender", ""), content=content,
            msg_type=raw.get("msg_type", "text"), media_urls=media_urls,
            ts=int(raw.get("ts", 0) or 0),
        )

    # ── 媒体下载 ──
    def _download_media(self, media_id: str) -> str | None:
        if not media_id or media_id.startswith("MEDIA"):
            return None
        try:
            token = self._get_token()
            resp = httpx.get(_MEDIA_URL, params={
                "access_token": token, "media_id": media_id}, timeout=30)
            if resp.status_code != 200 or resp.content.startswith(b"{"):
                return None   # 错误 JSON（如 media_id 过期）
            ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            ext = _EXT_MAP.get(ctype, "bin")
            from core import media as media_mod
            return media_mod.save_bytes("workwechat", media_id[:16], 0,
                                        resp.content, ext, f"media_{media_id[:10]}", self.username)
        except Exception as e:  # noqa: BLE001
            print(f"[workwechat] 媒体下载异常: {e}")
            return None

    # ── 语音转文字（尽力而为；企微语音为 amr/silk，成功率取决于转写服务支持） ──
    def _transcribe(self, local_path: str) -> str:
        import asyncio

        from config import DATA_DIR
        from core import analyzer
        p = DATA_DIR / local_path
        if not p.exists():
            return ""
        try:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(analyzer.transcribe_audio(self.config, str(p)))
            finally:
                loop.close()
        except Exception as e:  # noqa: BLE001
            print(f"[workwechat] 语音转写失败: {e}")
            return ""

    def health(self) -> dict:
        return {**super().health(), "token_ok": bool(self._token)}
