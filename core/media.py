"""
媒体保存器：把消息附件/图片下载保存到本地 data/media/，返回相对路径
目录结构: data/media/{platform}/{YYYY-MM-DD}/{msg_id}_{index}.{ext}
"""
from __future__ import annotations

import datetime
import re

from config import DATA_DIR

MEDIA_ROOT = DATA_DIR / "media"

# 扩展名 → 类型
_EXT_TYPE = {
    "jpg": "image", "jpeg": "image", "png": "image", "gif": "image", "webp": "image", "bmp": "image",
    "pdf": "document", "doc": "document", "docx": "document", "txt": "document", "md": "document",
    "xls": "table", "xlsx": "table", "csv": "table",
    "ppt": "slide", "pptx": "slide",
    "zip": "archive", "rar": "archive", "7z": "archive", "tar": "archive", "gz": "archive",
    "mp3": "audio", "wav": "audio", "amr": "audio", "silk": "audio",
    "mp4": "video", "mov": "video", "avi": "video", "mkv": "video", "flv": "video",
}


def guess_type(ext: str, url: str = "", name: str = "") -> str:
    """根据扩展名/URL/文件名推断文件类型"""
    if ext:
        return _EXT_TYPE.get(ext.lower(), "other")
    low = (url or "").lower()
    if any(m in low for m in (".jpg", ".jpeg", ".png", ".gif", ".webp")):
        return "image"
    if ".pdf" in low:
        return "document"
    if any(m in low for m in (".xls", ".xlsx", ".csv")):
        return "table"
    return "other"


def sanitize_name(name: str) -> str:
    """清洗文件名（防路径注入）"""
    name = (name or "file").replace("\\", "_").replace("/", "_")
    name = re.sub(r"[^\w.\-\u4e00-\u9fa5 ]", "_", name)
    return name[:80] or "file"


def save_bytes(platform: str, msg_id: str, index: int, data: bytes,
               ext: str, orig_name: str = "", username: str = "") -> str:
    """保存二进制到媒体目录，返回相对路径（如 media/qq/2026-08-27/xxx_0.jpg）
    多租户：username 指定时保存到该用户目录（data/users/{user}/media/），
    否则保存到全局 data/media/（兼容旧数据）
    原始文件名优先（含真实扩展名）；无扩展名时才补 ext"""
    date = datetime.date.today().isoformat()
    if username:
        from config import user_media_dir
        root = user_media_dir(username, platform)
    else:
        root = MEDIA_ROOT / platform
    sub = root / date
    sub.mkdir(parents=True, exist_ok=True)
    ext = (ext or "").lstrip(".").lower() or "bin"
    if orig_name:
        safe = sanitize_name(orig_name)
        # 原始名已有扩展名 → 直接用（不追加重复后缀）；无扩展名 → 补 ext
        if "." in safe and safe.rsplit(".", 1)[-1].lower() in (
                "jpg", "jpeg", "png", "gif", "webp", "bmp", "heic", "mp4", "mov",
                "3gp", "mp3", "amr", "wav", "pdf", "doc", "docx", "xls", "xlsx",
                "ppt", "pptx", "zip", "rar", "7z", "txt", "md"):
            filename = safe
        elif "." in safe:
            # 原始名带未知扩展名但和 ext 不同 → 用 ext 替换末尾扩展名
            filename = f"{safe.rsplit('.', 1)[0]}.{ext}"
        else:
            filename = f"{safe}.{ext}"
    else:
        filename = f"file_{msg_id[:12]}_{index}.{ext}"
    # 冲突则加序号
    path = sub / filename
    n = 1
    while path.exists():
        stem = path.stem
        path = sub / f"{stem}_{n}.{ext}"
        n += 1
    path.write_bytes(data)
    prefix = f"users/{username}/media/{platform}" if username else f"media/{platform}"
    return f"{prefix}/{date}/{path.name}"
