"""
飞书开放平台机器人适配器（长连接 WebSocket push 模式，无需公网回调）
- token: POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal (2h 自动刷新)
- 长连接: POST https://open.feishu.cn/open-apis/ws/v1/endpoints?ws_type=normal → wss 端点
- 事件: im.message.receive_v1（需在飞书开放平台订阅「接收消息」事件）
- 媒体: 图片/语音/文件通过 open-apis/im/v1 下载（需开通对应权限）
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime

import httpx

from core.adapter import PlatformAdapter
from core.models import ChatMessage

_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
_WS_ENDPOINT_URL = "https://open.feishu.cn/open-apis/ws/v1/endpoints?ws_type=normal"
_IMAGE_URL = "https://open.feishu.cn/open-apis/im/v1/images/{key}"
_FILE_URL = "https://open.feishu.cn/open-apis/im/v1/files/{key}?type={ftype}"

_EXT_MAP = {
    "image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png",
    "image/gif": "gif", "image/webp": "webp", "image/heic": "heic",
    "image/bmp": "bmp", "audio/ogg": "ogg", "audio/opus": "opus",
    "audio/amr": "amr", "audio/mpeg": "mp3", "audio/mp3": "mp3",
    "audio/x-wav": "wav", "video/mp4": "mp4", "application/pdf": "pdf",
}


def _parse_content(message: dict) -> tuple[str, str, list]:
    """解析飞书消息 → (文本, 类型, 媒体列表[{type,file_key,name}])"""
    msg_type = message.get("msg_type", "text")
    raw = message.get("content", "{}")
    try:
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        return str(data)[:200], "other", []
    if msg_type == "text":
        return (data.get("text") or "").strip() or "[空消息]", "text", []
    if msg_type == "post":   # 富文本：提取 title + 各文本段
        parts = []
        for row in data.get("content") or []:
            for seg in row or []:
                if isinstance(seg, dict) and seg.get("tag") == "text" and seg.get("text"):
                    parts.append(seg["text"])
                elif isinstance(seg, dict) and seg.get("tag") == "a" and seg.get("text"):
                    parts.append(f"{seg['text']}({seg.get('href', '')})")
        title = (data.get("title") or "").strip()
        text = (" ".join(parts).strip() or title or "[富文本]")
        return text, "text", []
    if msg_type == "image":
        return "[图片]", "image", [{"type": "image", "file_key": data.get("image_key", "")}]
    if msg_type == "audio":
        return "[语音]", "audio", [{"type": "audio", "file_key": data.get("file_key", "")}]
    if msg_type in ("file", "media"):
        fname = data.get("file_name", "")
        return f"[{msg_type}] {fname}".strip(), msg_type, [
            {"type": msg_type, "file_key": data.get("file_key", ""), "name": fname}]
    if msg_type == "sticker":
        return "[表情]", "sticker", [{"type": "sticker", "file_key": data.get("file_key", "")}]
    return "[其他消息]", "other", []


class FeishuAdapter(PlatformAdapter):
    name = "feishu"

    def __init__(self, config: dict, username: str = ""):
        super().__init__(config, username)
        self._token = ""
        self._token_expire = 0.0
        self._group_filter: set[str] = {
            g for g in (config.get("FEISHU_CHAT_IDS") or "").split(",") if g.strip()}

    # ── 鉴权 ──
    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expire - 60:
            return self._token
        resp = httpx.post(_TOKEN_URL, json={
            "app_id": self.config.get("FEISHU_APP_ID", ""),
            "app_secret": self.config.get("FEISHU_APP_SECRET", ""),
        }, timeout=15)
        data = resp.json()
        self._token = data.get("tenant_access_token", "")
        self._token_expire = time.time() + int(data.get("expire", 7200))
        if not self._token:
            raise RuntimeError(f"飞书 token 获取失败: {data}")
        return self._token

    def _get_ws_endpoint(self, token: str) -> str:
        resp = httpx.post(_WS_ENDPOINT_URL,
                          headers={"Authorization": f"Bearer {token}"}, timeout=15)
        data = resp.json()
        url = (data.get("data") or {}).get("url", "")
        if not url:
            raise RuntimeError(f"飞书长连接端点获取失败: {data}")
        return url

    # ── 连接与主循环 ──
    def _connect(self) -> None:
        pass  # token/端点均在 ws 循环里按需获取

    def _run_loop(self) -> None:
        while self._running:
            try:
                asyncio.run(self._ws_loop())
            except Exception as e:  # noqa: BLE001
                print(f"[feishu] WS 异常: {e}")
            if self._running:
                time.sleep(5)  # 重连间隔

    async def _ws_loop(self) -> None:
        import websockets
        token = self._get_token()
        endpoint = self._get_ws_endpoint(token)
        print(f"[feishu] 连接长连接: {endpoint[:80]}…")

        async with websockets.connect(endpoint, max_size=None, ping_interval=None) as ws:
            hb_task: asyncio.Task | None = None
            # 飞书协议：连接后必须先主动注册
            await ws.send(json.dumps({"type": "ClientRegister", "client_type": 1}))

            async def _heartbeat():
                # 25s 心跳保活；send 失败（连接已死）→ 主动 close，让主循环 recv 感知断开
                while self._running:
                    await asyncio.sleep(25)
                    try:
                        await ws.send(json.dumps({"type": "ClientHeartbeat"}))
                    except Exception:
                        try:
                            await ws.close()
                        except Exception:
                            pass
                        break

            while self._running:
                # 无限等待事件：飞书服务端不主动回心跳包，事件稀疏时固定超时会导致
                # 周期性误判重连 → 改为靠心跳线程 send 失败检测断线
                try:
                    raw = await ws.recv()
                except Exception:
                    print("[feishu] 连接断开，重连")
                    break
                try:
                    data = json.loads(raw)
                except Exception:
                    continue
                mtype = data.get("type", "")

                if mtype == "ClientRegisterSuccess":
                    print("[feishu] 已注册，开始接收消息")
                    if hb_task is None:
                        hb_task = asyncio.create_task(_heartbeat())
                elif mtype == "Event":
                    await self._handle_event(data)
                elif mtype == "ClientDisconnect":
                    print(f"[feishu] 服务端断开: {data.get('code', '')} {data.get('message', '')}")
                    break
                # 其他（如 URLVerification / Challenge 校验事件）忽略

            if hb_task:
                hb_task.cancel()
                try:
                    await asyncio.gather(hb_task, return_exceptions=True)
                except Exception:
                    pass

    # ── 事件解析 ──
    async def _handle_event(self, data: dict) -> None:
        header = data.get("header", {}) or {}
        if header.get("event_type") != "im.message.receive_v1":
            return
        event = data.get("event", {}) or {}
        message = event.get("message", {}) or {}
        if message.get("chat_type") != "group":
            return   # 只监控群聊（定位与 QQ 一致）
        chat_id = message.get("chat_id", "")
        if self._group_filter and chat_id not in self._group_filter:
            return
        content, mtype, media = _parse_content(message)
        local_media: list[str] = []
        for i, mi in enumerate(media):
            local = await self._download_one(mi, message.get("message_id", ""), i)
            if local:
                local_media.append(local)
            elif mi.get("file_key"):
                local_media.append(mi["file_key"])   # 下载失败保留占位
        # 语音转文字（复用百炼 paraformer-v2；失败保留占位）
        if mtype == "audio" and local_media:
            text = self._transcribe(local_media[0])
            content = f"🎤 [语音] 转写：{text}" if text else "[语音]（已保存，转写失败）"
        if not content and not local_media:
            content = "[无文本消息]"
        sender = event.get("sender", {}) or {}
        sender_id = (sender.get("sender_id") or {})
        self._emit(ChatMessage(
            msg_id=f"feishu_{message.get('message_id', '')}",
            platform="feishu", group_id=chat_id, group_name=chat_id[-8:] or "飞书群",
            sender=sender_id.get("open_id") or sender_id.get("user_id") or "",
            content=content, msg_type=mtype, media_urls=local_media,
            ts=int(message.get("create_time", "0") or 0),
        ))

    # ── 语音转文字（尽力而为） ──
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
            print(f"[feishu] 语音转写失败: {e}")
            return ""

    # ── 媒体下载 ──
    async def _download_one(self, mi: dict, msg_id: str, index: int) -> str | None:
        fk = mi.get("file_key", "")
        if not fk:
            return None
        try:
            mtype = mi.get("type", "image")
            if mtype == "image":
                url = _IMAGE_URL.format(key=fk)
            else:
                url = _FILE_URL.format(key=fk, ftype=mtype)
            token = self._get_token()
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
                if resp.status_code != 200:
                    print(f"[feishu] 媒体下载失败 {resp.status_code}: {fk[:40]}")
                    return None
                ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                ext = _EXT_MAP.get(ctype, "bin")
                from core import media as media_mod
                name = mi.get("name") or f"{mtype}_{fk[:10]}"
                return media_mod.save_bytes("feishu", msg_id[:16], index,
                                            resp.content, ext, name, self.username)
        except Exception as e:  # noqa: BLE001
            print(f"[feishu] 媒体下载异常: {e}")
            return None

    def health(self) -> dict:
        return {**super().health(), "token_ok": bool(self._token)}
