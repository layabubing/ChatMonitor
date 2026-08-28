"""
QQ 开放平台机器人适配器（WebSocket push 模式）
- token: POST https://bots.qq.com/app/getAppAccessToken (2h 自动刷新)
- 网关: GET https://api.sgroup.qq.com/gateway（沙箱: sandbox.api.sgroup.qq.com）
- 事件: GROUP_MESSAGE_CREATE（全量模式，需开启「接收所有消息」）
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime

import httpx

from core.adapter import PlatformAdapter
from core.models import ChatMessage

_TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
_INTENT_GROUP_AND_C2C = 1 << 25   # 群聊+单聊事件
_MSG_TYPE_NAMES = {0: "text", 1: "text", 2: "markdown", 7: "media"}


def _rfc3339_to_ms(ts_str: str) -> int:
    """RFC3339 → 毫秒时间戳"""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return int(time.time() * 1000)


class QQAdapter(PlatformAdapter):
    name = "qq"

    def __init__(self, config: dict, username: str = ""):
        super().__init__(config, username)
        self._token = ""
        self._token_expire = 0.0
        self._group_filter: set[str] = {
            g for g in (config.get("QQ_GROUP_OPENIDS") or "").split(",") if g.strip()}

    # ── 鉴权 ──
    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expire - 60:
            return self._token
        resp = httpx.post(_TOKEN_URL, json={
            "appId": self.config.get("QQ_APP_ID", ""),
            "clientSecret": self.config.get("QQ_APP_SECRET", ""),
        }, timeout=15)
        data = resp.json()
        self._token = data.get("access_token", "")
        self._token_expire = time.time() + int(data.get("expires_in", 7200))
        if not self._token:
            raise RuntimeError(f"QQ token 获取失败: {data}")
        return self._token

    def _get_gateway(self, token: str) -> str:
        env = self.config.get("QQ_ENV", "prod")
        base = "https://sandbox.api.sgroup.qq.com" if env == "sandbox" else "https://api.sgroup.qq.com"
        resp = httpx.get(f"{base}/gateway", headers={"Authorization": f"QQBot {token}"}, timeout=15)
        return resp.json().get("url", "wss://api.sgroup.qq.com/websocket/")

    # ── 连接与主循环 ──
    def _connect(self) -> None:
        pass  # token/网关在 ws 循环里按需获取

    def _run_loop(self) -> None:
        while self._running:
            try:
                asyncio.run(self._ws_loop())
            except Exception as e:  # noqa: BLE001
                print(f"[qq] WS 异常: {e}")
            if self._running:
                time.sleep(5)  # 重连间隔

    async def _ws_loop(self) -> None:
        import websockets
        token = self._get_token()
        gateway = self._get_gateway(token)
        print(f"[qq] 连接网关: {gateway}")
        hb_interval = 30.0
        s = None

        async with websockets.connect(gateway, max_size=None, ping_interval=None) as ws:
            hb_task: asyncio.Task | None = None

            async def _heartbeat():
                while self._running:
                    await asyncio.sleep(hb_interval)
                    try:
                        await ws.send(json.dumps({"op": 1, "d": s}))
                    except Exception:
                        break

            while self._running:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=hb_interval * 2 + 10)
                except TimeoutError:
                    print("[qq] 心跳超时，重连")
                    break
                data = json.loads(raw)
                op = data.get("op", 0)

                if op == 10:  # Hello
                    hb_interval = data["d"]["heartbeat_interval"] / 1000
                    await ws.send(json.dumps({"op": 2, "d": {
                        "token": f"QQBot {token}",
                        "intents": _INTENT_GROUP_AND_C2C,
                        "shard": [0, 1],
                        "properties": {"$os": "linux", "$browser": "chat-monitor", "$device": "chat-monitor"},
                    }}))
                    hb_task = asyncio.create_task(_heartbeat())
                elif op == 0:  # Dispatch
                    s = data.get("s")
                    t = data.get("t")
                    if t == "GROUP_MESSAGE_CREATE":
                        await self._handle_group_msg(data.get("d", {}))
                    elif t == "READY":
                        print("[qq] 已连接，开始接收群消息")
                # op 1/11 心跳相关，忽略

            if hb_task:
                hb_task.cancel()
                try:
                    await asyncio.gather(hb_task, return_exceptions=True)
                except Exception:
                    pass

    # ── 消息解析 ──
    async def _handle_group_msg(self, d: dict) -> None:
        group_openid = d.get("group_openid", "")
        if self._group_filter and group_openid not in self._group_filter:
            return
        content = d.get("content", "") or ""
        msg_type, media_items = self._parse_media(d)
        content = self._clean_faces(content)
        # 语音消息：使用 QQ 官方内置转写 asr_refer_text（免费）
        if msg_type == "voice" and not content:
            asr = self._find_asr(d)
            if asr:
                content = f"🎤 [语音] 转写：{asr}"
        # 下载媒体到本地 data/media/；下载失败不存外网 URL（QQ 防盗链不可用）
        local_media: list[str] = []
        for i, m in enumerate(media_items):
            local = await self._download_one(d, m, i)
            if local:
                local_media.append(local)
        if not content and not local_media:
            content = "[无文本消息]"
        self._emit(ChatMessage(
            msg_id=f"qq_{d.get('id', '')}",
            platform="qq", group_id=group_openid, group_name=group_openid[-8:] or "QQ群",
            sender=(d.get("author") or {}).get("username", ""),
            content=content, msg_type=msg_type, media_urls=local_media,
            ts=_rfc3339_to_ms(d.get("timestamp", "")),
        ))

    @staticmethod
    def _find_asr(d: dict) -> str:
        """从消息数据里找 QQ 官方语音转写 asr_refer_text（支持嵌套，如 voice 子对象）"""
        def _dig(obj, depth=0):
            if depth > 4:
                return ""
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ("asr_refer_text", "asrReferText", "asr_refer") and isinstance(v, str) and v.strip():
                        return v.strip()
                    r = _dig(v, depth + 1)
                    if r:
                        return r
            elif isinstance(obj, list):
                for it in obj:
                    r = _dig(it, depth + 1)
                    if r:
                        return r
            return ""
        return _dig(d)

    @staticmethod
    def _clean_faces(content: str) -> str:
        """表情识别：解析 <faceType=6,faceId="x",ext="base64"> 中的真实 emoji 文本；
        无法解析的图片表情回退为 [表情]"""
        import base64
        import json as _json
        import re

        def repl(m: re.Match) -> str:
            ext = m.group(1) if m.lastindex and m.lastindex >= 1 else ""
            if ext:
                try:
                    data = _json.loads(base64.b64decode(ext).decode("utf-8", "ignore"))
                    text = (data.get("text") or "").strip()
                    if text:
                        return text
                except Exception:
                    pass
            return "[表情]"

        # 带 ext 的表情：尝试解出真实 emoji
        content = re.sub(r'<faceType=\d+[^>]*ext="([^"]*)"[^>]*>', repl, content)
        # 无 ext 的兜底
        content = re.sub(r"<faceType=\d+[^>]*>", "[表情]", content)
        return content.strip()

    async def _download_one(self, d: dict, m: dict, index: int) -> str | None:
        """下载单个媒体附件到本地，返回相对路径；失败返回 None。
        实况图/视频处理：优先按服务端响应的 Content-Type 决定扩展名（最准确）"""
        url = m.get("url", "")
        if not url:
            return None
        try:
            import re as _re

            import httpx

            from core import media as media_mod
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    print(f"[qq] 媒体下载失败 {resp.status_code}: {url[:60]}")
                    return None
                name = m.get("name", "") or ""
                # 扩展名优先级：Content-Type（最准）→ 原始名 → URL → 类型 fallback
                ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                ctype_map = {
                    "image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png",
                    "image/gif": "gif", "image/webp": "webp", "image/heic": "heic",
                    "image/bmp": "bmp", "video/mp4": "mp4", "video/quicktime": "mov",
                    "video/3gpp": "3gp", "audio/mpeg": "mp3", "audio/amr": "amr",
                    "audio/x-wav": "wav", "application/pdf": "pdf",
                }
                ext = ctype_map.get(ctype, "")
                if not ext and name and "." in name:
                    cand = name.rsplit(".", 1)[-1].strip().lower()
                    if len(cand) <= 5 and cand.isalnum():
                        ext = cand
                if not ext:
                    murl = _re.search(r"\.([a-z0-9]{2,5})(?:$|[?&])", url.lower())
                    if murl:
                        ext = murl.group(1)
                if not ext:
                    ftype = media_mod.guess_type("", url, name)
                    ext = {"image": "jpg", "document": "pdf", "table": "xlsx",
                           "slide": "pptx", "video": "mp4", "audio": "amr",
                           "archive": "zip"}.get(ftype, "bin")
                # 实况图通常是视频+图片双 attachment；如果 content_type 是 application/octet-stream
                # 但 URL 像是视频（QQ 多媒体域名）→ 强制 mp4
                if (ctype.startswith("application/octet-stream")
                        and "multimedia" in url.lower()):
                    ext = "mp4"
                local = media_mod.save_bytes("qq", d.get("id", "msg"), index,
                                             resp.content, ext, name, self.username)
                return local
        except Exception as e:  # noqa: BLE001
            print(f"[qq] 媒体下载异常: {e}")
            return None

    def _parse_media(self, d: dict) -> tuple[str, list[dict]]:
        """解析媒体：返回 (msg_type, 媒体列表[{url,name,type}])"""
        media_items: list[dict] = []
        msg_type = "text"
        for att in d.get("attachments") or []:
            if att.get("url"):
                media_items.append({"url": att["url"], "name": att.get("filename", ""),
                                    "type": "image" if att.get("content_type", "").startswith("image") else "file"})
                msg_type = "image" if att.get("content_type", "").startswith("image") else "media"
        for el in d.get("msg_elements") or []:
            etype = el.get("type", 0)
            if etype == 2:  # 图片
                msg_type = "image"
                if el.get("element_id") and not media_items:
                    # 富媒体：标记为需下载（官方下载接口带签名，暂存占位）
                    media_items.append({"url": "", "name": f"image_{el.get('element_id', '')[:10]}.jpg",
                                        "type": "image", "element_id": el.get("element_id")})
            elif etype == 3:  # 语音
                if msg_type == "text":
                    msg_type = "voice"
                if el.get("element_id") and not any(m.get("element_id") == el.get("element_id") for m in media_items):
                    media_items.append({"url": "", "name": f"voice_{el.get('element_id', '')[:10]}",
                                        "type": "voice", "element_id": el.get("element_id")})
            elif etype == 7:  # 富媒体(视频/文件)
                if msg_type == "text":
                    msg_type = "media"
                if el.get("element_id") and not any(m.get("element_id") == el.get("element_id") for m in media_items):
                    media_items.append({"url": "", "name": f"media_{el.get('element_id', '')[:10]}",
                                        "type": "media", "element_id": el.get("element_id")})
        return msg_type, media_items

    def health(self) -> dict:
        return {**super().health(), "token_ok": bool(self._token)}
