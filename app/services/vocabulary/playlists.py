# app/services/vocabulary/playlists.py
"""WordLens 自定义歌单（播放列表）CRUD。

内置分组（待复习 / 不认识 / 模糊 / 认识）都能由既有查询直接算出来，不落库；
这里只负责用户手挑单词攒出来的歌单。歌单里的顺序由 position 列决定，整体替换
词表时按传入数组的下标重写，读取时按它排序——用户在编辑页排的顺序就是播放顺序。
"""
from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vocabulary import VocabularyPlaylist, VocabularyPlaylistItem, VocabularyWord


def dedupe_word_ids(word_ids: list[uuid.UUID], owned_ids: set[uuid.UUID]) -> list[uuid.UUID]:
    """按输入顺序去重，并过滤掉不属于当前用户的 id。

    越权 id 静默丢弃而不是报错：客户端可能带着刚被另一台设备删掉的词提交，
    整个请求失败对用户没有意义，保留其余的词更符合预期。

    Args:
        word_ids: 客户端传来的单词 id 列表（可能有重复、可能夹带别人的词）
        owned_ids: 当前用户生词库里实际存在的单词 id

    Returns:
        去重且只保留 owned_ids 中的 id，顺序与 word_ids 中首次出现的顺序一致
    """
    result: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for word_id in word_ids:
        if word_id in seen or word_id not in owned_ids:
            continue
        seen.add(word_id)
        result.append(word_id)
    return result


async def _owned_word_ids(session: AsyncSession, user_id: uuid.UUID, word_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """从候选 id 中筛出确实属于该用户的那些。"""
    if not word_ids:
        return set()
    stmt = select(VocabularyWord.id).where(
        VocabularyWord.user_id == user_id, VocabularyWord.id.in_(word_ids)
    )
    res = await session.execute(stmt)
    return set(res.scalars().all())


async def _replace_items(session: AsyncSession, playlist_id: uuid.UUID, word_ids: list[uuid.UUID]) -> None:
    """整体替换歌单词表：先清空再按下标写 position（不 commit，由调用方统一提交）。"""
    await session.execute(
        delete(VocabularyPlaylistItem).where(VocabularyPlaylistItem.playlist_id == playlist_id)
    )
    for position, word_id in enumerate(word_ids):
        session.add(
            VocabularyPlaylistItem(playlist_id=playlist_id, word_id=word_id, position=position)
        )


async def get_playlist(
    session: AsyncSession, user_id: uuid.UUID, playlist_id: uuid.UUID
) -> VocabularyPlaylist | None:
    """按 id 获取歌单（校验属于该用户）。"""
    stmt = select(VocabularyPlaylist).where(
        VocabularyPlaylist.id == playlist_id, VocabularyPlaylist.user_id == user_id
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def list_playlists(
    session: AsyncSession, user_id: uuid.UUID
) -> list[tuple[VocabularyPlaylist, int]]:
    """歌单列表，每个歌单附带词数。

    用 outer join + count 一次查完，避免「先查歌单再逐个 count」的 N+1。
    """
    stmt = (
        select(VocabularyPlaylist, func.count(VocabularyPlaylistItem.id))
        .outerjoin(VocabularyPlaylistItem, VocabularyPlaylistItem.playlist_id == VocabularyPlaylist.id)
        .where(VocabularyPlaylist.user_id == user_id)
        .group_by(VocabularyPlaylist.id)
        .order_by(VocabularyPlaylist.created_at.desc())
    )
    res = await session.execute(stmt)
    return [(playlist, count) for playlist, count in res.all()]


async def create_playlist(
    session: AsyncSession, user_id: uuid.UUID, name: str, word_ids: list[uuid.UUID]
) -> tuple[VocabularyPlaylist, int]:
    """新建歌单，返回歌单与最终词数（越权/重复的 id 已被过滤掉）。"""
    owned = await _owned_word_ids(session, user_id, word_ids)
    valid_ids = dedupe_word_ids(word_ids, owned)

    playlist = VocabularyPlaylist(user_id=user_id, name=name)
    session.add(playlist)
    # 先 flush 拿到 playlist.id 才能写 items，最后一起 commit。
    await session.flush()
    await _replace_items(session, playlist.id, valid_ids)
    await session.commit()
    await session.refresh(playlist)
    return playlist, len(valid_ids)


async def update_playlist(
    session: AsyncSession,
    user_id: uuid.UUID,
    playlist_id: uuid.UUID,
    name: str | None = None,
    word_ids: list[uuid.UUID] | None = None,
) -> tuple[VocabularyPlaylist, int] | None:
    """改名 / 整体替换词表。两个参数都可选，传 None 表示这一项不动。"""
    playlist = await get_playlist(session, user_id, playlist_id)
    if playlist is None:
        return None

    if name is not None:
        playlist.name = name
        session.add(playlist)

    if word_ids is not None:
        owned = await _owned_word_ids(session, user_id, word_ids)
        valid_ids = dedupe_word_ids(word_ids, owned)
        await _replace_items(session, playlist.id, valid_ids)
        count = len(valid_ids)
    else:
        count = await count_playlist_words(session, playlist.id)

    await session.commit()
    await session.refresh(playlist)
    return playlist, count


async def add_words_to_playlist(
    session: AsyncSession, user_id: uuid.UUID, playlist_id: uuid.UUID, word_ids: list[uuid.UUID]
) -> tuple[VocabularyPlaylist, int] | None:
    """把一批词并入歌单末尾（已在歌单里的跳过）。

    生词库多选「加入歌单」走这个接口而不是 update_playlist：那边是整体替换，
    客户端得先把歌单现有词表拉下来再拼，多一次往返也容易和别的设备互相覆盖。
    """
    playlist = await get_playlist(session, user_id, playlist_id)
    if playlist is None:
        return None

    owned = await _owned_word_ids(session, user_id, word_ids)
    candidates = dedupe_word_ids(word_ids, owned)

    existing_stmt = select(VocabularyPlaylistItem.word_id).where(
        VocabularyPlaylistItem.playlist_id == playlist_id
    )
    existing_res = await session.execute(existing_stmt)
    existing_ids = set(existing_res.scalars().all())

    max_stmt = select(func.max(VocabularyPlaylistItem.position)).where(
        VocabularyPlaylistItem.playlist_id == playlist_id
    )
    max_res = await session.execute(max_stmt)
    # 空歌单时 max() 返回 NULL，从 0 开始排。这里必须显式判 None 而不是写
    # `or -1`：已有一个词时 max 就是 0，`0 or -1` 会取到 -1，新词又从 0 开始，
    # 于是两个词挤在同一个 position 上、顺序变得不确定。
    max_position = max_res.scalar_one_or_none()
    next_position = 0 if max_position is None else max_position + 1

    for word_id in candidates:
        if word_id in existing_ids:
            continue
        session.add(
            VocabularyPlaylistItem(playlist_id=playlist_id, word_id=word_id, position=next_position)
        )
        next_position += 1

    await session.commit()
    await session.refresh(playlist)
    # 词数重新 count 而不是用 next_position 推算：单词被删掉时它的 item 会被一起
    # 清掉（见 words.delete_word），position 就出现空洞，推算出来的数会偏大。
    return playlist, await count_playlist_words(session, playlist_id)


async def delete_playlist(session: AsyncSession, user_id: uuid.UUID, playlist_id: uuid.UUID) -> bool:
    """删除歌单，成功返回 True，不存在返回 False。

    items 没有 ON DELETE CASCADE，必须先删干净否则外键约束会拦下来——
    跟 words.delete_word 处理 review_logs 是同一个套路。
    """
    playlist = await get_playlist(session, user_id, playlist_id)
    if playlist is None:
        return False
    await session.execute(
        delete(VocabularyPlaylistItem).where(VocabularyPlaylistItem.playlist_id == playlist_id)
    )
    await session.delete(playlist)
    await session.commit()
    return True


async def count_playlist_words(session: AsyncSession, playlist_id: uuid.UUID) -> int:
    """歌单里的词数。"""
    stmt = select(func.count(VocabularyPlaylistItem.id)).where(
        VocabularyPlaylistItem.playlist_id == playlist_id
    )
    res = await session.execute(stmt)
    return res.scalar_one()


async def get_playlist_words(
    session: AsyncSession, user_id: uuid.UUID, playlist_id: uuid.UUID
) -> list[VocabularyWord] | None:
    """歌单词表，按 position 排序。歌单不存在（或不属于该用户）时返回 None。"""
    playlist = await get_playlist(session, user_id, playlist_id)
    if playlist is None:
        return None
    stmt = (
        select(VocabularyWord)
        .join(VocabularyPlaylistItem, VocabularyPlaylistItem.word_id == VocabularyWord.id)
        .where(VocabularyPlaylistItem.playlist_id == playlist_id)
        .order_by(VocabularyPlaylistItem.position.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())
