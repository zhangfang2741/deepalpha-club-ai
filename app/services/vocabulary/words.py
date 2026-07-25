# app/services/vocabulary/words.py
"""生词库 CRUD 与去重逻辑。"""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vocabulary import VocabularyReviewLog, VocabularyWord
from app.services.vocabulary import sm2


def _naive_utc_now() -> datetime.datetime:
    """返回不带时区的 UTC 当前时间，匹配 naive 的 TIMESTAMP 列类型。

    vocabulary_words/vocabulary_review_logs 的时间列是 TIMESTAMP WITHOUT TIME ZONE，
    asyncpg 对带时区的 datetime 会直接报 DataError，这里统一转成 naive UTC 再落库/比较。
    """
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


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


async def get_existing_words(session: AsyncSession, user_id: uuid.UUID) -> set[str]:
    """返回某用户生词库中所有单词（原始大小写）。"""
    stmt = select(VocabularyWord.word).where(VocabularyWord.user_id == user_id)
    res = await session.execute(stmt)
    return set(res.scalars().all())


async def create_words_batch(
    session: AsyncSession, user_id: uuid.UUID, words: list[dict]
) -> list[VocabularyWord]:
    """批量插入生词（调用方已去重）。"""
    now = _naive_utc_now()
    rows = [
        VocabularyWord(
            user_id=user_id,
            word=w["word"],
            phonetic_ipa=w["phonetic_ipa"],
            part_of_speech=w["part_of_speech"],
            definition_zh=w["definition_zh"],
            etymology=w.get("etymology", ""),
            example_sentence=w.get("example_sentence", ""),
            status="new",
            next_review_at=now,
        )
        for w in words
    ]
    session.add_all(rows)
    await session.commit()
    for row in rows:
        await session.refresh(row)
    return rows


async def add_words_with_dedup(
    session: AsyncSession, user_id: uuid.UUID, words: list[dict]
) -> tuple[list[VocabularyWord], list[str]]:
    """批量加入生词库并自动去重。

    Returns:
        (新建的单词行, 被跳过的重复词原文)
    """
    existing = await get_existing_words(session, user_id)
    existing_lower = {w.lower() for w in existing}
    seen_lower: set[str] = set()
    to_create: list[dict] = []
    skipped: list[str] = []
    for w in words:
        lower = w["word"].lower()
        if lower in existing_lower or lower in seen_lower:
            skipped.append(w["word"])
            continue
        seen_lower.add(lower)
        to_create.append(w)
    created = await create_words_batch(session, user_id, to_create)
    return created, skipped


async def list_words(
    session: AsyncSession, user_id: uuid.UUID, status: str | None = None, query: str | None = None
) -> list[VocabularyWord]:
    """生词库列表，支持按状态筛选和关键词搜索。"""
    stmt = select(VocabularyWord).where(VocabularyWord.user_id == user_id)
    if status:
        stmt = stmt.where(VocabularyWord.status == status)
    if query:
        stmt = stmt.where(VocabularyWord.word.ilike(f"%{query}%"))
    stmt = stmt.order_by(VocabularyWord.created_at.desc())
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_word(session: AsyncSession, user_id: uuid.UUID, word_id: uuid.UUID) -> VocabularyWord | None:
    """按 id 获取单词详情（校验属于该用户）。"""
    stmt = select(VocabularyWord).where(VocabularyWord.id == word_id, VocabularyWord.user_id == user_id)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def delete_word(session: AsyncSession, user_id: uuid.UUID, word_id: uuid.UUID) -> bool:
    """删除单词，成功返回 True，不存在返回 False。

    先删除该单词的复习历史（VocabularyReviewLog 无 ON DELETE CASCADE），
    否则一旦复习过一次就会因外键约束删不掉。
    """
    word = await get_word(session, user_id, word_id)
    if word is None:
        return False
    await session.execute(delete(VocabularyReviewLog).where(VocabularyReviewLog.word_id == word_id))
    await session.delete(word)
    await session.commit()
    return True


async def get_review_queue(session: AsyncSession, user_id: uuid.UUID) -> list[VocabularyWord]:
    """待复习队列：next_review_at <= now，按到期时间升序。"""
    now = _naive_utc_now()
    stmt = (
        select(VocabularyWord)
        .where(VocabularyWord.user_id == user_id, VocabularyWord.next_review_at <= now)
        .order_by(VocabularyWord.next_review_at.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def submit_review(
    session: AsyncSession, user_id: uuid.UUID, word_id: uuid.UUID, rating: int
) -> VocabularyWord | None:
    """提交一次复习结果：跑 SM-2、更新单词状态、写复习日志。"""
    word = await get_word(session, user_id, word_id)
    if word is None:
        return None

    result = sm2.apply_review(
        rating=rating,
        repetition_count=word.repetition_count,
        easiness_factor=word.easiness_factor,
        interval_days=word.interval_days,
    )
    reviewed_at = _naive_utc_now()
    log = VocabularyReviewLog(
        word_id=word.id,
        rating=rating,
        reviewed_at=reviewed_at,
        interval_before=word.interval_days,
        interval_after=result.interval_days,
    )
    word.repetition_count = result.repetition_count
    word.easiness_factor = result.easiness_factor
    word.interval_days = result.interval_days
    # sm2.apply_review 返回带时区的 next_review_at，这里的列是 naive UTC，落库前去掉 tzinfo
    word.next_review_at = result.next_review_at.replace(tzinfo=None)
    word.last_reviewed_at = reviewed_at
    word.status = result.status

    session.add(word)
    session.add(log)
    await session.commit()
    await session.refresh(word)
    return word
