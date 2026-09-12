# app/services/vocabulary/libraries.py
"""内置词库（kajweb/dict 精选）读取与导入逻辑。

词库数据由 scripts/build_vocabulary_libraries.py 离线生成，落在
app/data/vocabulary_libraries/ 下：manifest.json 描述分组与每本元信息，
<book_id>.json 是该本的精简词条数组。运行时只读、体积固定，用 lru_cache
读一次常驻内存，避免每次请求都读盘和反序列化。
"""
from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.vocabulary import words as word_service

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "vocabulary_libraries"

# 单次 INSERT 的分块大小：asyncpg 单条语句参数上限约 32767，VocabularyWord 每行
# 约 8 个参数，专八 12197 词一次插会爆参数上限，按每块 1000 词切开写。
_IMPORT_CHUNK_SIZE = 1000


@lru_cache(maxsize=1)
def _load_manifest() -> dict:
    """读取并缓存 manifest.json（分组 + 每本元信息）。"""
    path = _DATA_DIR / "manifest.json"
    if not path.exists():
        return {"groups": []}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _book_index() -> dict[str, dict]:
    """book_id -> 元信息（含所属分组 key/title）的索引。"""
    index: dict[str, dict] = {}
    for group in _load_manifest().get("groups", []):
        for book in group.get("books", []):
            index[book["id"]] = {
                **book,
                "group_key": group["key"],
                "group_title": group["title"],
            }
    return index


def list_groups() -> list[dict]:
    """返回全部分组及其词库元信息（不含词条本身），供前端渲染选择列表。"""
    return _load_manifest().get("groups", [])


def get_book_meta(book_id: str) -> dict | None:
    """返回单本词库元信息；不存在返回 None。"""
    return _book_index().get(book_id)


@lru_cache(maxsize=8)
def get_book_words(book_id: str) -> tuple[dict, ...]:
    """读取并缓存单本词库的全部精简词条。

    返回 tuple 而非 list，配合 lru_cache 保证缓存值不可变、不被调用方误改。
    只缓存最近用到的 8 本，避免把 42 本全部（含专八 12197 词）常驻内存。
    """
    path = _DATA_DIR / f"{book_id}.json"
    if not path.exists():
        return ()
    data = json.loads(path.read_text(encoding="utf-8"))
    return tuple(data)


async def import_book(
    session: AsyncSession, user_id: uuid.UUID, book_id: str
) -> tuple[int, int]:
    """把一本内置词库整本并入用户生词库，自动跨全库去重。

    大词库分块写入，避开 asyncpg 单语句参数上限；每块内部及与已有生词库之间
    都做大小写不敏感去重（复用 words.add_words_with_dedup）。

    Returns:
        (新增词数, 跳过的已存在词数)
    """
    entries = get_book_words(book_id)
    total_created = 0
    total_skipped = 0
    for start in range(0, len(entries), _IMPORT_CHUNK_SIZE):
        chunk = [dict(w) for w in entries[start : start + _IMPORT_CHUNK_SIZE]]
        created, skipped = await word_service.add_words_with_dedup(session, user_id, chunk)
        total_created += len(created)
        total_skipped += len(skipped)
    return total_created, total_skipped
