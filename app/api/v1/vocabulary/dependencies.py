# app/api/v1/vocabulary/dependencies.py
"""WordLens 独立账户体系的鉴权依赖。"""
from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.vocabulary import VocabularyUser
from app.services.vocabulary import users as user_service
from app.utils.auth import verify_token
from app.utils.sanitization import sanitize_string

security = HTTPBearer()


async def get_current_vocab_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> VocabularyUser:
    """从 JWT 解析并返回当前 WordLens 用户。"""
    token = sanitize_string(credentials.credentials)
    raw_user_id = verify_token(token)
    if raw_user_id is None:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    try:
        user_id = uuid.UUID(raw_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid token format") from exc

    user = await user_service.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user
