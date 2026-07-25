# app/services/vocabulary/users.py
"""VocabularyUser 账号 DB 操作。"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vocabulary import VocabularyUser


async def get_user_by_email(session: AsyncSession, email: str) -> VocabularyUser | None:
    """按邮箱查找用户。"""
    stmt = select(VocabularyUser).where(VocabularyUser.email == email)
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
