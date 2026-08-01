# app/services/vocabulary/words.py
"""生词库 CRUD 与去重逻辑。"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.vocabulary import VocabularyPlaylistItem, VocabularyReviewLog, VocabularyWord
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


async def create_words_batch(session: AsyncSession, user_id: uuid.UUID, words: list[dict]) -> list[VocabularyWord]:
    """批量插入生词（调用方已去重）。

    INSERT ... RETURNING 一次性把刚写入的行回填到 ORM 对象，避免以前那种
    `for row in rows: await session.refresh(row)` 的 N 次串行 SELECT：100 个
    词要 100 次往返 DB，HTTP keep-alive 通道在这段时间里几乎没有 payload
    反向回压，Railway 边缘代理经常把这条连接 RST 掉（实测 -1005 "网络连
    接已中断"）。改 RETURNING 后所有回表压力压缩到 1 次往返，下游
    `VocabularyWordResponse.model_validate(r)` 访问字段不会再触发隐式
    refresh——行实例本身就是 RETURNING 拿回来的新鲜数据，不在 session
    expire-on-commit 的过期名单里。
    """
    now = _naive_utc_now()
    values = [
        {
            "user_id": user_id,
            "word": w["word"],
            "phonetic_ipa": w["phonetic_ipa"],
            "part_of_speech": w["part_of_speech"],
            "definition_zh": w["definition_zh"],
            "etymology": w.get("etymology", ""),
            "example_sentence": w.get("example_sentence", ""),
            "status": "new",
            "next_review_at": now,
        }
        for w in words
    ]
    if not values:
        return []
    stmt = insert(VocabularyWord).values(values).returning(VocabularyWord)
    result = await session.execute(stmt)
    await session.commit()
    return list(result.scalars())


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

    先删除该单词的复习历史和歌单归属（VocabularyReviewLog /
    VocabularyPlaylistItem 都没有 ON DELETE CASCADE），否则一旦复习过一次、
    或者被加进过任何一个歌单，就会因外键约束删不掉。
    """
    word = await get_word(session, user_id, word_id)
    if word is None:
        return False
    await session.execute(delete(VocabularyReviewLog).where(VocabularyReviewLog.word_id == word_id))
    await session.execute(delete(VocabularyPlaylistItem).where(VocabularyPlaylistItem.word_id == word_id))
    await session.delete(word)
    await session.commit()
    return True


async def delete_words_batch(session: AsyncSession, user_id: uuid.UUID, word_ids: list[uuid.UUID]) -> int:
    """在一个事务中批量删除当前用户的生词及其关联记录。

    先筛出确实属于当前用户的 ID，再用集合 DELETE 清理复习日志、分组关联和
    单词本身。无效、重复或已被另一端删除的 ID 会被忽略，因此接口可安全重试。
    """
    unique_ids = list(dict.fromkeys(word_ids))
    if not unique_ids:
        return 0

    owned_stmt = select(col(VocabularyWord.id)).where(
        col(VocabularyWord.user_id) == user_id,
        col(VocabularyWord.id).in_(unique_ids),
    )
    owned_res = await session.execute(owned_stmt)
    owned_ids = list(owned_res.scalars().all())
    if not owned_ids:
        return 0

    await session.execute(delete(VocabularyReviewLog).where(col(VocabularyReviewLog.word_id).in_(owned_ids)))
    await session.execute(delete(VocabularyPlaylistItem).where(col(VocabularyPlaylistItem.word_id).in_(owned_ids)))
    await session.execute(
        delete(VocabularyWord).where(
            col(VocabularyWord.user_id) == user_id,
            col(VocabularyWord.id).in_(owned_ids),
        )
    )
    await session.commit()
    return len(owned_ids)


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


async def get_stats(session: AsyncSession, user_id: uuid.UUID) -> dict[str, int]:
    """生词库各分组计数：待复习数 + 三个状态各多少 + 总数。

    两条聚合查询搞定，不把词表本身拉下来——iOS 的播放列表面板每次打开都要这几个
    数字，传几百条完整词条只为显示四个数太浪费。

    Returns:
        含 due_count / new_count / fuzzy_count / known_count / total_count 的 dict
    """
    now = _naive_utc_now()
    status_stmt = (
        select(VocabularyWord.status, func.count(VocabularyWord.id))
        .where(VocabularyWord.user_id == user_id)
        .group_by(VocabularyWord.status)
    )
    status_res = await session.execute(status_stmt)
    by_status = {status: count for status, count in status_res.all()}

    due_stmt = select(func.count(VocabularyWord.id)).where(
        VocabularyWord.user_id == user_id, VocabularyWord.next_review_at <= now
    )
    due_res = await session.execute(due_stmt)

    return {
        "due_count": due_res.scalar_one(),
        "new_count": by_status.get("new", 0),
        "fuzzy_count": by_status.get("fuzzy", 0),
        "known_count": by_status.get("known", 0),
        "total_count": sum(by_status.values()),
    }


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
