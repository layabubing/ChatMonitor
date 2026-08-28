"""
全局默认关键词库：configs/important_keywords.json 的加载/保存/匹配。
（用户级关键词库见 core/accounts/keywords.py）

关键词命中是「双重判定」的第一层过滤，命中后再交 AI 确认重要性。
"""
from __future__ import annotations

import json
import os

from config import CONFIGS_DIR

_KEYWORDS_FILE = CONFIGS_DIR / "important_keywords.json"
_ALL_KEYWORDS: list[str] = []


def load_keywords() -> list[str]:
    """加载关键词库（展开所有类别，去重保序）。"""
    global _ALL_KEYWORDS
    try:
        data = json.loads(_KEYWORDS_FILE.read_text(encoding="utf-8"))
        words = [w for group in data.values() for w in group]
        _ALL_KEYWORDS = list(dict.fromkeys(words))
    except Exception as e:  # noqa: BLE001
        print(f"[keywords] 关键词加载失败: {e}")
        _ALL_KEYWORDS = []
    return _ALL_KEYWORDS


def save_keywords(categories: dict) -> None:
    """保存关键词库（UI 设置页调用；临时文件 + rename 原子写防损坏）。"""
    tmp = _KEYWORDS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(categories, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, _KEYWORDS_FILE)
    load_keywords()


def get_keyword_categories() -> dict:
    try:
        return json.loads(_KEYWORDS_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def all_keywords() -> list[str]:
    return _ALL_KEYWORDS


def match(text: str, words: list[str] | None = None) -> bool:
    """判断文本是否命中关键词；words 为空时用全局词库。"""
    pool = words if words is not None else _ALL_KEYWORDS
    if not pool or not text:
        return False
    return any(k in text for k in pool)
