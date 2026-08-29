"""
跨进程消息收件箱：web 回调进程写入 → worker 轮询消费（复用 commands 通道的文件模式）
场景：企业微信回调消息由 web 进程接收，需转交给独立 worker 进程的 pipeline。

文件格式: data/inbox/{platform}/[{scope}/]{msg_id}.json  (ChatMessage 兼容 dict + 路由字段)
- 消费即删除（同 commands 模式）；按 msg_id 天然去重
- scope：消息含 corpid 时自动落入 {platform}/{corpid}/ 子目录，
  worker 各实例只消费自己 corpid 的子目录 → 消除多租户并发消费竞态
"""
from __future__ import annotations

import json
from pathlib import Path

from config import DATA_DIR


def _dir(platform: str, scope: str = "") -> Path:
    if scope:
        return DATA_DIR / "inbox" / platform / scope
    return DATA_DIR / "inbox" / platform


def push_message(platform: str, msg: dict) -> bool:
    """web 进程调用：投递一条平台消息。msg 必须含 msg_id（用于去重/文件名）；
    含 corpid 时按 corpid 分目录（多租户隔离，避免 worker 多实例竞争）。"""
    msg_id = str(msg.get("msg_id", "")).strip()
    if not msg_id:
        return False
    scope = str(msg.get("corpid", "") or "").strip()
    d = _dir(platform, scope)
    d.mkdir(parents=True, exist_ok=True)
    # 文件名转义（msg_id 可能含平台特殊字符）
    safe = "".join(ch for ch in msg_id if ch.isalnum() or ch in "-_.") or "m"
    target = d / f"{safe}.json"
    tmp = d / f".{safe}.tmp"
    try:
        tmp.write_text(json.dumps(msg, ensure_ascii=False), encoding="utf-8")
        tmp.replace(target)   # 原子写，防 worker 读到半截文件
        return True
    except Exception:  # noqa: BLE001
        try:
            tmp.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        return False


def pop_messages(platform: str, scope: str = "") -> list[dict]:
    """worker 进程调用：消费并清空收件箱，返回消息 dict 列表。
    scope 非空时只消费 {platform}/{scope}/ 子目录（多租户：每实例只读自己 corpid 的消息）。"""
    d = _dir(platform, scope)
    if not d.exists():
        return []
    out: list[dict] = []
    for p in sorted(d.glob("*.json")):
        try:
            raw = p.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                out.append(data)
        except Exception:  # noqa: BLE001  损坏文件跳过不阻塞
            pass
        finally:
            try:
                p.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass
    return out


def pending_count(platform: str, scope: str = "") -> int:
    """web 查询：收件箱待处理消息数（只读）。"""
    d = _dir(platform, scope)
    if not d.exists():
        return 0
    try:
        return len(list(d.glob("*.json")))
    except Exception:  # noqa: BLE001
        return 0
