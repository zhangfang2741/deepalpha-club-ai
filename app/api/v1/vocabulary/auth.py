# app/api/v1/vocabulary/auth.py
"""WordLens 独立注册/登录路由（不复用主站 /auth）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.session import get_db
from app.models.vocabulary import VocabularyUser
from app.schemas.vocabulary import (
    VocabularyLoginRequest,
    VocabularyTokenResponse,
    VocabularyUserCreate,
)
from app.services.vocabulary import users as user_service
from app.utils.auth import create_access_token
from app.utils.sanitization import sanitize_email, validate_password_strength

router = APIRouter()


@router.post("/register", response_model=VocabularyTokenResponse)
async def register(payload: VocabularyUserCreate, db: AsyncSession = Depends(get_db)):
    """注册新 WordLens 账号。"""
    email = sanitize_email(payload.email)
    password = payload.password.get_secret_value()
    validate_password_strength(password)

    existing = await user_service.get_user_by_email(db, email)
    if existing is not None:
        raise HTTPException(status_code=400, detail="该邮箱已被注册")

    hashed = VocabularyUser.hash_password(password)
    user = await user_service.create_user(db, email, hashed)
    token = create_access_token(str(user.id))
    logger.info("vocabulary_user_registered", user_id=str(user.id))
    return VocabularyTokenResponse(access_token=token.access_token, expires_at=token.expires_at)


@router.post("/login", response_model=VocabularyTokenResponse)
async def login(payload: VocabularyLoginRequest, db: AsyncSession = Depends(get_db)):
    """WordLens 账号登录。"""
    email = sanitize_email(payload.email)
    user = await user_service.get_user_by_email(db, email)
    if user is None or not user.verify_password(payload.password.get_secret_value()):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    token = create_access_token(str(user.id))
    logger.info("vocabulary_user_logged_in", user_id=str(user.id))
    return VocabularyTokenResponse(access_token=token.access_token, expires_at=token.expires_at)
