"""
钉钉适配器：官方企业内部应用 API，轮询拉取群消息（pull 模式）
- token: POST https://api.dingtalk.com/v1.0/oauth2/accessToken
- 历史消息: POST https://oapi.dingtalk.com/chat/getChatHistory
权限: qyapi_chat_read（需管理员授权）
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from config import DATA_DIR
from core.adapter import PlatformAdapter
from core.models import ChatMessage

_TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
_HISTORY_URL = "https://oapi.dingtalk.com/chat/getChatHistory"
_MEDIA_DOWNLOAD_URL = "https://oapi.dingtalk.com/media/download"
_MAX_PAGES = 20


def _parse_content(raw: str) -> tuple[str, str, list]:
    """解析钉钉消息 content JSON → (文本, 类型, 媒体列表[{type,media_id,name,...}])"""
    try:
        data = json.loads(raw)
    except Exception:
        return raw, "text", []
    if not isinstance(data, dict):
        return str(data), "text", []
    if "content" in data:
        return str(data["content"]), "text", []
    if data.get("picMediaId"):
        return "[图片]", "image", [{"type": "image", "media_id": data["picMediaId"]}]
    if data.get("fileName"):
        mi = {"type": "file", "name": data.get("fileName", "")}
        if data.get("downloadCode"):
            mi["download_code"] = data["downloadCode"]
        if data.get("mediaId"):
            mi["media_id"] = data["mediaId"]
        return f"[文件] {data.get('fileName', '')}", "file", [mi]
    if data.get("videoMediaId"):
        return "[视频]", "video", [{"type": "video", "media_id": data["videoMediaId"]}]
    if data.get("mediaId"):
        return "[语音]", "audio", [{"type": "audio", "media_id": data["mediaId"]}]
    return json.dumps(data, ensure_ascii=False)[:200], "other", []


class DingTalkAdapter(PlatformAdapter):
    name = "dingtalk"

    def __init__(self, config: dict, username: str = ""):
        super().__init__(config, username)
        self._token = ""
        self._token_expire = 0.0
        self._cursors: dict[str, str] = {}   # chat_id -> 分页游标
        self._last_ts: dict[str, int] = {}   # chat_id -> 已处理最大时间戳(ms)
        self._load_cursors()

    # ── 语音转文字（百炼 paraformer-v2 异步转写，尽力而为） ──
    def _transcribe(self, local_path: str) -> str:
        import asyncio

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
            print(f"[dingtalk] 语音转写失败: {e}")
            return ""

    # ── 媒体下载（图片/语音用 media/download；文件 downloadCode 走新版接口，暂存占位） ──
    def _download_media(self, mi: dict, idx: int) -> str | None:
        media_id = mi.get("media_id", "")
        if not media_id or mi.get("type") == "file":
            # 文件类需要 downloadCode+jsticket 签名下载，暂不实现（保留 media_id 占位）
            return None
        try:
            token = self._ensure_token()
            resp = httpx.get(_MEDIA_DOWNLOAD_URL, params={"media_id": media_id, "access_token": token}, timeout=30)
            if resp.status_code != 200 or resp.content.startswith(b"{"):
                return None
            ctype = resp.headers.get("content-type", "")
            if "image" in ctype:
                ext = "jpg"
            elif "audio" in ctype:
                ext = "amr"
            else:
                ext = "bin"
            from core import media as media_mod
            name = mi.get("name") or f"media_{media_id[:10]}"
            return media_mod.save_bytes("dingtalk", media_id[:12], idx, resp.content, ext, name, self.username)
        except Exception as e:  # noqa: BLE001
            print(f"[dingtalk] 媒体下载失败: {e}")
            return None

    # ── 游标持久化（跨重启增量） ──
    def _cursor_file(self) -> Path:
        return DATA_DIR / "dingtalk_cursor.json"

    def _load_cursors(self) -> None:
        try:
            data = json.loads(self._cursor_file().read_text(encoding="utf-8"))
            self._cursors = data.get("cursors", {})
            self._last_ts = {k: int(v) for k, v in data.get("last_ts", {}).items()}
        except Exception:
            pass

    def _save_cursors(self) -> None:
        try:
            self._cursor_file().write_text(json.dumps(
                {"cursors": self._cursors, "last_ts": self._last_ts},
                ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass

    # ── 连接 ──
    def _connect(self) -> None:
        self._ensure_token()

    def _ensure_token(self) -> str:
        if self._token and time.time() < self._token_expire - 60:
            return self._token
        resp = httpx.post(_TOKEN_URL, json={
            "appKey": self.config.get("DINGTALK_APP_KEY", ""),
            "appSecret": self.config.get("DINGTALK_APP_SECRET", ""),
        }, timeout=15)
        data = resp.json()
        self._token = data.get("accessToken", "")
        self._token_expire = time.time() + int(data.get("expireIn", 7200))
        if not self._token:
            raise RuntimeError(f"钉钉 token 获取失败: {data}")
        return self._token

    # ── 拉取循环 ──
    def _run_loop(self) -> None:
        interval = max(10, int(self.config.get("POLL_INTERVAL", 90)))
        while self._running:
            try:
                self._poll_all()
            except Exception as e:  # noqa: BLE001
                print(f"[dingtalk] 轮询失败: {e}")
            self._save_cursors()
            for _ in range(interval * 5):
                if not self._running:
                    break
                time.sleep(0.2)

    def _poll_all(self) -> None:
        chat_ids = [c.strip() for c in self.config.get("DINGTALK_CHAT_IDS", "").split(",") if c.strip()]
        if not chat_ids:
            return
        token = self._ensure_token()
        for chat_id in chat_ids:
            try:
                self._poll_chat(chat_id, token)
            except Exception as e:  # noqa: BLE001
                print(f"[dingtalk] 群 {chat_id} 拉取失败: {e}")

    def _poll_chat(self, chat_id: str, token: str) -> None:
        cursor = self._cursors.get(chat_id, "")
        last_ts = self._last_ts.get(chat_id, 0)
        start_time = last_ts + 1 if last_ts else int((time.time() - 7 * 86400) * 1000)
        new_msgs: list[ChatMessage] = []
        max_ts = last_ts

        for _ in range(_MAX_PAGES):
            body: dict = {"chatid": chat_id, "size": 100}
            if cursor:
                body["cursor"] = cursor
            else:
                body["start_time"] = start_time
            resp = httpx.post(f"{_HISTORY_URL}?access_token={token}", json=body, timeout=20)
            data = resp.json()
            if data.get("errcode", 0) != 0:
                raise RuntimeError(f"钉钉历史消息失败: {data}")
            for m in data.get("messages", []):
                content, mtype, media = _parse_content(m.get("content", ""))
                ts = int(m.get("time", 0) or 0)
                if ts <= last_ts:
                    continue
                max_ts = max(max_ts, ts)
                # 下载媒体（图片/语音走 media/download）→ 本地路径
                local_media = []
                for i, mi in enumerate(media):
                    local = self._download_media(mi, i)
                    if local:
                        local_media.append(local)
                    elif mi.get("media_id"):
                        local_media.append(mi["media_id"])   # 下载失败保留占位
                # 语音转文字（百炼 paraformer-v2；失败则保留"[语音]（已保存）"）
                if mtype == "audio" and local_media:
                    text = self._transcribe(local_media[0])
                    content = f"🎤 [语音] 转写：{text}" if text else "[语音]（已保存，转写失败）"
                new_msgs.append(ChatMessage(
                    msg_id=f"dingtalk_{m.get('msg_id', ts)}",
                    platform="dingtalk", group_id=chat_id, group_name=f"群{chat_id[-4:]}",
                    sender=m.get("sender_nick", ""), content=content,
                    msg_type=mtype, media_urls=local_media, ts=ts,
                ))
            if not data.get("has_more"):
                break
            cursor = data.get("cursor", "")
            if not cursor:
                break

        # 记录最新游标/时间，供下次增量
        self._cursors[chat_id] = ""
        if max_ts > last_ts:
            self._last_ts[chat_id] = max_ts
        for m in new_msgs:
            self._emit(m)

    def health(self) -> dict:
        return {**super().health(), "token_ok": bool(self._token)}
