"""认证路由：注册、登录、会话管理。."""

import asyncio
import uuid
from typing import List

from fastapi import APIRouter, Depends, Form, HTTPException, Request

from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.session import Session
from app.models.user import User
from app.schemas.auth import (
    PasswordChange,
    SessionResponse,
    TokenResponse,
    UserCreate,
    UserProfileResponse,
    UserResponse,
    UserUpdate,
)
from app.services.database import database_service
from app.utils.auth import create_access_token
from app.utils.sanitization import sanitize_email, sanitize_string, validate_password_strength

from .dependencies import get_current_session, get_current_user

router = APIRouter()


@router.post("/register", response_model=UserResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["register"][0])
async def register_user(request: Request, user_data: UserCreate):
    """注册新用户。."""
    try:
        sanitized_email = sanitize_email(user_data.email)
        password = user_data.password.get_secret_value()
        validate_password_strength(password)

        # Check if user exists
        existing_user = await asyncio.to_thread(database_service.get_user_by_email, sanitized_email)
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "该邮箱已被注册",
                    "code": "EMAIL_ALREADY_EXISTS",
                    "field": "email"
                }
            )

        sanitized_username = sanitize_string(user_data.username) if user_data.username else None

        # Hash password in a thread pool to avoid blocking the event loop
        hashed_password = await asyncio.to_thread(User.hash_password, password)

        user = await asyncio.to_thread(
            database_service.create_user,
            sanitized_email,
            hashed_password,
            sanitized_username,
        )

        token = create_access_token(str(user.id))
        return UserResponse(id=user.id, email=user.email, username=user.username, token=token)
    except HTTPException:
        raise
    except ValueError as ve:
        logger.exception("user_registration_validation_failed", error=str(ve))
        # Parse validation errors into user-friendly messages
        error_msg = str(ve)
        field = "password"
        code = "VALIDATION_ERROR"
        
        if "uppercase" in error_msg.lower():
            message = "密码必须包含至少一个大写字母"
            code = "PASSWORD_NO_UPPERCASE"
        elif "lowercase" in error_msg.lower():
            message = "密码必须包含至少一个小写字母"
            code = "PASSWORD_NO_LOWERCASE"
        elif "number" in error_msg.lower():
            message = "密码必须包含至少一个数字"
            code = "PASSWORD_NO_NUMBER"
        elif "special" in error_msg.lower():
            message = "密码必须包含至少一个特殊字符（如 !@#$%^&*）"
            code = "PASSWORD_NO_SPECIAL"
        elif "8 characters" in error_msg.lower() or "8位" in error_msg:
            message = "密码长度至少需要 8 个字符"
            code = "PASSWORD_TOO_SHORT"
        elif "email format" in error_msg.lower():
            message = "邮箱格式不正确"
            code = "INVALID_EMAIL_FORMAT"
            field = "email"
        else:
            message = error_msg
        
        raise HTTPException(status_code=422, detail={"message": message, "code": code, "field": field})


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["login"][0])
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    grant_type: str = Form(default="password"),
):
    """用户登录。."""
    start_time = asyncio.get_event_loop().time()
    try:
        email = sanitize_string(email)
        password = sanitize_string(password)
        grant_type = sanitize_string(grant_type)

        if grant_type != "password":
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "不支持的授权类型，仅支持 'password'",
                    "code": "UNSUPPORTED_GRANT_TYPE"
                }
            )

        # 1. Database lookup
        db_start = asyncio.get_event_loop().time()
        user = await asyncio.to_thread(database_service.get_user_by_email, email)
        db_end = asyncio.get_event_loop().time()
        
        if not user:
            logger.warning("login_failed_user_not_found", email=email)
            raise HTTPException(
                status_code=401,
                detail={
                    "message": "邮箱或密码错误",
                    "code": "INVALID_CREDENTIALS"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 2. Password verification (offload to thread pool)
        verify_start = asyncio.get_event_loop().time()
        is_password_correct = await asyncio.to_thread(user.verify_password, password)
        verify_end = asyncio.get_event_loop().time()

        if not is_password_correct:
            logger.warning("login_failed_wrong_password", user_id=user.id)
            raise HTTPException(
                status_code=401,
                detail={
                    "message": "邮箱或密码错误",
                    "code": "INVALID_CREDENTIALS"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 3. Token creation
        token_start = asyncio.get_event_loop().time()
        token = create_access_token(str(user.id))
        token_end = asyncio.get_event_loop().time()

        total_duration = asyncio.get_event_loop().time() - start_time
        logger.info(
            "login_successful",
            user_id=user.id,
            duration_ms=round(total_duration * 1000, 2),
            db_ms=round((db_end - db_start) * 1000, 2),
            verify_ms=round((verify_end - verify_start) * 1000, 2),
            token_ms=round((token_end - token_start) * 1000, 2),
        )

        return TokenResponse(access_token=token.access_token, token_type="bearer", expires_at=token.expires_at)
    except HTTPException:
        raise
    except ValueError as ve:
        logger.exception("login_validation_failed", error=str(ve))
        raise HTTPException(status_code=422, detail={"message": str(ve), "code": "VALIDATION_ERROR"})


@router.post("/session", response_model=SessionResponse)
async def create_session(user: User = Depends(get_current_user)):
    """创建新的聊天会话。."""
    try:
        session_id = str(uuid.uuid4())
        session = await asyncio.to_thread(database_service.create_session, session_id, user.id, "", user.username)
        token = create_access_token(session_id)

        logger.info(
            "session_created",
            session_id=session_id,
            user_id=user.id,
            name=session.name,
            expires_at=token.expires_at.isoformat(),
        )

        return SessionResponse(session_id=session_id, name=session.name, token=token)
    except ValueError as ve:
        logger.exception("session_creation_validation_failed", error=str(ve), user_id=user.id)
        raise HTTPException(status_code=422, detail=str(ve))


@router.patch("/session/{session_id}/name", response_model=SessionResponse)
async def update_session_name(
    session_id: str,
    name: str = Form(...),
    current_session: Session = Depends(get_current_session),
):
    """更新会话名称。."""
    try:
        sanitized_session_id = sanitize_string(session_id)
        sanitized_name = sanitize_string(name)
        sanitized_current_session = sanitize_string(current_session.id)

        if sanitized_session_id != sanitized_current_session:
            raise HTTPException(status_code=403, detail="Cannot modify other sessions")

        session = await asyncio.to_thread(
            database_service.update_session_name, sanitized_session_id, sanitized_name
        )
        token = create_access_token(sanitized_session_id)

        return SessionResponse(session_id=sanitized_session_id, name=session.name, token=token)
    except ValueError as ve:
        logger.exception("session_update_validation_failed", error=str(ve), session_id=session_id)
        raise HTTPException(status_code=422, detail=str(ve))


@router.delete("/session/{session_id}")
async def delete_session(session_id: str, current_session: Session = Depends(get_current_session)):
    """删除会话。."""
    try:
        sanitized_session_id = sanitize_string(session_id)
        sanitized_current_session = sanitize_string(current_session.id)

        if sanitized_session_id != sanitized_current_session:
            raise HTTPException(status_code=403, detail="Cannot delete other sessions")

        await asyncio.to_thread(database_service.delete_session, sanitized_session_id)
        logger.info("session_deleted", session_id=session_id, user_id=current_session.user_id)
    except ValueError as ve:
        logger.exception("session_deletion_validation_failed", error=str(ve), session_id=session_id)
        raise HTTPException(status_code=422, detail=str(ve))


@router.get("/sessions", response_model=List[SessionResponse])
async def get_user_sessions(user: User = Depends(get_current_user)):
    """获取用户所有会话。."""
    try:
        sessions = await asyncio.to_thread(database_service.get_user_sessions, user.id)
        return [
            SessionResponse(
                session_id=sanitize_string(session.id),
                name=sanitize_string(session.name),
                token=create_access_token(session.id),
            )
            for session in sessions
        ]
    except ValueError as ve:
        logger.exception("get_sessions_validation_failed", user_id=user.id, error=str(ve))
        raise HTTPException(status_code=422, detail=str(ve))


# ============ User Settings Endpoints ============

@router.get("/me", response_model=UserProfileResponse)
async def get_current_user_profile(user: User = Depends(get_current_user)):
    """获取当前用户个人资料。"""
    try:
        return UserProfileResponse(
            id=user.id,
            email=user.email,
            username=user.username,
            created_at=user.created_at,
        )
    except Exception as e:
        logger.exception("get_user_profile_failed", user_id=user.id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get user profile")


@router.patch("/me", response_model=UserProfileResponse)
async def update_user_profile(
    update_data: UserUpdate,
    user: User = Depends(get_current_user),
):
    """更新当前用户个人资料。"""
    try:
        sanitized_username = sanitize_string(update_data.username) if update_data.username else None
        
        updated_user = await asyncio.to_thread(
            database_service.update_user,
            user_id=user.id,
            username=sanitized_username,
        )
        
        logger.info("user_profile_updated", user_id=user.id)
        
        return UserProfileResponse(
            id=updated_user.id,
            email=updated_user.email,
            username=updated_user.username,
            created_at=updated_user.created_at,
        )
    except Exception as e:
        logger.exception("update_user_profile_failed", user_id=user.id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to update user profile")


@router.post("/me/password", response_model=dict)
async def change_password(
    password_data: PasswordChange,
    user: User = Depends(get_current_user),
):
    """修改当前用户密码。"""
    try:
        # Verify current password
        current_password = password_data.current_password.get_secret_value()
        is_password_correct = await asyncio.to_thread(user.verify_password, current_password)
        
        if not is_password_correct:
            logger.warning("password_change_failed_wrong_current", user_id=user.id)
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "当前密码不正确",
                    "code": "INVALID_CURRENT_PASSWORD"
                }
            )
        
        # Validate new password strength
        new_password = password_data.new_password.get_secret_value()
        validate_password_strength(new_password)
        
        # Hash new password
        hashed_password = await asyncio.to_thread(User.hash_password, new_password)
        
        # Update password in database
        await asyncio.to_thread(
            database_service.update_user,
            user_id=user.id,
            hashed_password=hashed_password,
        )
        
        logger.info("password_changed_successfully", user_id=user.id)
        
        return {"message": "密码修改成功"}
    except HTTPException:
        raise
    except ValueError as ve:
        logger.exception("password_validation_failed", user_id=user.id, error=str(ve))
        error_msg = str(ve)
        
        if "uppercase" in error_msg.lower():
            message = "新密码必须包含至少一个大写字母"
        elif "lowercase" in error_msg.lower():
            message = "新密码必须包含至少一个小写字母"
        elif "number" in error_msg.lower():
            message = "新密码必须包含至少一个数字"
        elif "special" in error_msg.lower():
            message = "新密码必须包含至少一个特殊字符（如 !@#$%^&*）"
        elif "8 characters" in error_msg.lower() or "8位" in error_msg:
            message = "新密码长度至少需要 8 个字符"
        else:
            message = error_msg
        
        raise HTTPException(status_code=422, detail={"message": message, "code": "VALIDATION_ERROR"})
    except Exception as e:
        logger.exception("change_password_failed", user_id=user.id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to change password")
