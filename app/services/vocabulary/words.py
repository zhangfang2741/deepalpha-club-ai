"""生词库 CRUD 与去重逻辑。"""
from __future__ import annotations


def filter_new_words(existing_words: set[str], candidates: list[str]) -> list[str]:
    """过滤掉已在生词库中的候选词（大小写不敏感），保留候选词原始大小写与顺序。

    Args:
        existing_words: 生词库中已存在的单词（原始大小写，内部转小写比较）
        candidates: 候选词列表（原始大小写）

    Returns:
        candidates 中尚未加入生词库的词，内部按小写去重，保留第一次出现的大小写
    """
    existing_lower = {w.lower() for w in existing_words}
    result: list[str] = []
    seen_lower: set[str] = set()
    for word in candidates:
        lower = word.lower()
        if lower in existing_lower or lower in seen_lower:
            continue
        seen_lower.add(lower)
        result.append(word)
    return result
