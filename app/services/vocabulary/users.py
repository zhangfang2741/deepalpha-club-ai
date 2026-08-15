# app/services/vocabulary/users.py
"""VocabularyUser 账号 DB 操作。"""
from __future__ import annotations

import uuid

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.vocabulary import (
    VocabularyPlaylist,
    VocabularyPlaylistItem,
    VocabularyReviewLog,
    VocabularyUser,
    VocabularyWord,
)


async def get_user_by_email(session: AsyncSession, email: str) -> VocabularyUser | None:
    """按邮箱查找用户。"""
    stmt = select(VocabularyUser).where(col(VocabularyUser.email) == email)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> VocabularyUser | None:
    """按 id 查找用户。"""
    return await session.get(VocabularyUser, user_id)


async def create_user(session: AsyncSession, email: str, hashed_password: str) -> VocabularyUser:
    """创建新用户。"""
    user = VocabularyUser(email=email, hashed_password=hashed_password)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def change_password(session: AsyncSession, user: VocabularyUser, new_password: str) -> None:
    """更新用户密码（调用方已校验旧密码）。"""
    user.hashed_password = VocabularyUser.hash_password(new_password)
    session.add(user)
    await session.commit()


async def delete_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    """彻底删除用户及其全部数据，一个事务内完成。

    App Store 审核指南 5.1.1(v)：有注册功能就必须提供 App 内自助删除账号，
    且要真删——不做软删除、不留宽限期。

    vocabulary_* 几张表只声明了 foreign_key，没有 ON DELETE CASCADE，所以
    必须按依赖顺序自己删，顺序错了直接撞外键约束：

        playlist_items → review_logs → playlists → words → user

    歌单条目同时外键到 playlist 和 word，两条路径都要清：只按 playlist 删的话，
    「别的歌单引用了本用户的词」这种残留会在删 words 时把事务顶回来。
    """
    user_word_ids = select(col(VocabularyWord.id)).where(col(VocabularyWord.user_id) == user_id)
    user_playlist_ids = select(col(VocabularyPlaylist.id)).where(col(VocabularyPlaylist.user_id) == user_id)

    await session.execute(
        delete(VocabularyPlaylistItem).where(
            or_(
                col(VocabularyPlaylistItem.playlist_id).in_(user_playlist_ids),
                col(VocabularyPlaylistItem.word_id).in_(user_word_ids),
            )
        )
    )
    await session.execute(delete(VocabularyReviewLog).where(col(VocabularyReviewLog.word_id).in_(user_word_ids)))
    await session.execute(delete(VocabularyPlaylist).where(col(VocabularyPlaylist.user_id) == user_id))
    await session.execute(delete(VocabularyWord).where(col(VocabularyWord.user_id) == user_id))
    await session.execute(delete(VocabularyUser).where(col(VocabularyUser.id) == user_id))
    await session.commit()
