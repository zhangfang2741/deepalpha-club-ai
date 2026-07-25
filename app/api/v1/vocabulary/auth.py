# app/api/v1/vocabulary/auth.py
"""WordLens 独立注册/登录路由（不复用主站 /auth）。

不用 `from __future__ import annotations`：slowapi 的 @limiter.limit() 装饰器会
让 FastAPI 把 body 参数的类型注解解析成未展开的 ForwardRef，body 会被误判成
query 参数，导致 422（这个文件的每个路由都挂了限流装饰器）。
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import logger
from app.db.session import get_db
from app.models.vocabulary import VocabularyUser
from app.schemas.vocabulary import (
    ChangePasswordRequest,
    VocabularyLoginRequest,
    VocabularyTokenResponse,
    VocabularyUserCreate,
    VocabularyUserResponse,
)
from app.services.vocabulary import users as user_service
from app.utils.auth import create_access_token
from app.utils.sanitization import sanitize_email, validate_vocabulary_password_strength

from .dependencies import get_current_vocab_user

router = APIRouter()


@router.post("/register", response_model=VocabularyTokenResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["register"][0])
async def register(request: Request, payload: VocabularyUserCreate, db: AsyncSession = Depends(get_db)):
    """注册新 WordLens 账号。"""
    try:
        email = sanitize_email(payload.email)
        password = payload.password.get_secret_value()
        validate_vocabulary_password_strength(password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = await user_service.get_user_by_email(db, email)
    if existing is not None:
        raise HTTPException(status_code=400, detail="该邮箱已被注册")

    hashed = VocabularyUser.hash_password(password)
    user = await user_service.create_user(db, email, hashed)
    token = create_access_token(str(user.id))
    logger.info("vocabulary_user_registered", user_id=str(user.id))
    return VocabularyTokenResponse(access_token=token.access_token, expires_at=token.expires_at)


@router.post("/login", response_model=VocabularyTokenResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["login"][0])
async def login(request: Request, payload: VocabularyLoginRequest, db: AsyncSession = Depends(get_db)):
    """WordLens 账号登录。"""
    try:
        email = sanitize_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    user = await user_service.get_user_by_email(db, email)
    if user is None or not user.verify_password(payload.password.get_secret_value()):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    token = create_access_token(str(user.id))
    logger.info("vocabulary_user_logged_in", user_id=str(user.id))
    return VocabularyTokenResponse(access_token=token.access_token, expires_at=token.expires_at)


@router.get("/me", response_model=VocabularyUserResponse)
async def get_me(user: VocabularyUser = Depends(get_current_vocab_user)):
    """当前登录用户的个人信息。"""
    return VocabularyUserResponse.model_validate(user)


@router.post("/change-password")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["vocabulary_change_password"][0])
async def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """修改当前用户密码，需校验旧密码。"""
    if not user.verify_password(payload.old_password.get_secret_value()):
        raise HTTPException(status_code=401, detail="原密码不正确")
    try:
        validate_vocabulary_password_strength(payload.new_password.get_secret_value())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await user_service.change_password(db, user, payload.new_password.get_secret_value())
    logger.info("vocabulary_password_changed", user_id=str(user.id))
    return {"changed": True}
