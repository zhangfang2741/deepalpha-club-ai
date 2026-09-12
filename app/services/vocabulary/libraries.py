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
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.vocabulary import VocabularyWord
from app.services.vocabulary import playlists as playlist_service
from app.services.vocabulary import words as word_service

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "vocabulary_libraries"

# 单次 INSERT 的分块大小：asyncpg 单条语句参数上限约 32767，VocabularyWord 每行
# 约 8 个参数，专八 12197 词一次插会爆参数上限，按每块 1000 词切开写。
_IMPORT_CHUNK_SIZE = 1000

# 歌单名（VocabularyPlaylist.name）列宽上限，超长截断。
_PLAYLIST_NAME_MAX = 50


@dataclass
class ImportResult:
    """导入一本内置词库的结果。

    imported/skipped 为本次写库的新增/跳过词数；playlist_* 描述与词库同名、
    自动建/刷新的歌单——用户可在首页切到它单独复习这本、单独看进度。
    """

    imported: int
    skipped: int
    playlist_id: uuid.UUID
    playlist_name: str
    playlist_word_count: int


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


async def _lookup_word_ids_in_book_order(
    session: AsyncSession, user_id: uuid.UUID, lower_words: list[str]
) -> list[uuid.UUID]:
    """按词库原始顺序，查出这些词在用户生词库里对应的 id。

    生词库与词库都可能存在大小写差异，按 lower(word) 匹配；分块查询把 IN 参数量
    控制在 asyncpg 上限内。同一小写词只取一次（去重时保留的那条）。
    """
    id_by_lower: dict[str, uuid.UUID] = {}
    for start in range(0, len(lower_words), _IMPORT_CHUNK_SIZE):
        chunk = lower_words[start : start + _IMPORT_CHUNK_SIZE]
        stmt = select(col(VocabularyWord.id), col(VocabularyWord.word)).where(
            col(VocabularyWord.user_id) == user_id,
            func.lower(col(VocabularyWord.word)).in_(chunk),
        )
        res = await session.execute(stmt)
        for word_id, word in res.all():
            lower = word.lower()
            if lower not in id_by_lower:
                id_by_lower[lower] = word_id
    return [id_by_lower[lw] for lw in lower_words if lw in id_by_lower]


async def import_book(session: AsyncSession, user_id: uuid.UUID, book_id: str) -> ImportResult:
    """把一本内置词库整本并入用户生词库，并建/刷新与它同名的歌单。

    - 大词库分块写入，避开 asyncpg 单语句参数上限；每块内部及与已有生词库之间
      都做大小写不敏感去重（复用 words.add_words_with_dedup），已存在的词保留
      原有的 SM-2 记忆进度、绝不重置。
    - 导入后按词库名建（或整体替换）一个歌单，收录本词库在生词库里的**全部**词
      （新导入的 + 之前已存在被跳过的），保持词库原始顺序。这样每本词库都能作为
      独立歌单进入、只复习这一本，而进度始终跟随单词本身。重复导入只会把歌单
      刷新成最新的完整词表，幂等。
    """
    entries = get_book_words(book_id)
    total_created = 0
    total_skipped = 0
    for start in range(0, len(entries), _IMPORT_CHUNK_SIZE):
        chunk = [dict(w) for w in entries[start : start + _IMPORT_CHUNK_SIZE]]
        created, skipped = await word_service.add_words_with_dedup(session, user_id, chunk)
        total_created += len(created)
        total_skipped += len(skipped)

    meta = get_book_meta(book_id)
    playlist_name = (meta["title"] if meta else book_id)[:_PLAYLIST_NAME_MAX]
    # 词库内已按小写去重，这里保序取小写即为歌单的目标顺序。
    lower_words = [e["word"].lower() for e in entries]
    ordered_ids = await _lookup_word_ids_in_book_order(session, user_id, lower_words)
    playlist, count = await playlist_service.replace_or_create_playlist_by_name(
        session, user_id, playlist_name, ordered_ids
    )
    return ImportResult(
        imported=total_created,
        skipped=total_skipped,
        playlist_id=playlist.id,
        playlist_name=playlist.name,
        playlist_word_count=count,
    )
