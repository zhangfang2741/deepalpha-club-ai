"""认证路由：注册、登录、会话管理。."""

import asyncio
import secrets
import uuid
from typing import List

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from redis.asyncio import Redis

from app.cache.client import get_redis
from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.session import Session
from app.models.user import User
from app.schemas.auth import (
    AccountLoginRequest,
    AppleLoginRequest,
    EmailCodeRequest,
    EmailPasswordResetConfirm,
    EmailRegisterRequest,
    PasswordChange,
    PhoneCodeRequest,
    PhonePasswordResetConfirm,
    PhoneRegisterRequest,
    SessionResponse,
    TokenResponse,
    UserCreate,
    UserProfileResponse,
    UserResponse,
    UserUpdate,
)
from app.services import email as email_service
from app.services.account import codes
from app.services.account.accounts import AccountKind, resolve_account
from app.services.apple_auth import AppleAuthError, verify_identity_token
from app.services.database import database_service
from app.services.verification_code import (
    Purpose,
    ResendTooSoonError,
    TooManyAttemptsError,
)
from app.utils.auth import create_access_token
from app.utils.phone import InvalidPhoneError, normalize_phone
from app.utils.sanitization import sanitize_email, sanitize_string, validate_password_strength

from .dependencies import get_current_session, get_current_user

router = APIRouter()


def _raise_for_delivery(exc: Exception) -> None:
    """Translate codes-layer exceptions into HTTP responses.

    服务层不认识 HTTP 状态码，翻译集中在这里一处，避免九个端点各写一遍
    try/except 金字塔。
    """
    if isinstance(exc, ResendTooSoonError):
        raise HTTPException(
            status_code=429,
            detail=f"验证码已发送，请 {settings.EMAIL_CODE_RESEND_COOLDOWN} 秒后再试",
        ) from None
    if isinstance(exc, codes.DailySendLimitError):
        raise HTTPException(
            status_code=429,
            detail="该号码今日获取验证码次数过多，请明天再试或改用邮箱注册",
        ) from None
    if isinstance(exc, codes.GlobalSendLimitError):
        # 全站预算熔断：可能是被短信轰炸刷了，也可能是真实流量涨了。记 warning
        # 让运维能从日志/告警发现，再决定是调高预算还是排查攻击。不向用户暴露细节。
        logger.warning("sms_global_daily_budget_exhausted")
        raise HTTPException(
            status_code=429, detail="验证码服务繁忙，请稍后再试"
        ) from None
    if isinstance(exc, codes.CodeChannelUnavailableError):
        raise HTTPException(status_code=503, detail="验证码服务暂不可用，请稍后再试") from None
    if isinstance(exc, codes.CodeDeliveryError):
        raise HTTPException(status_code=502, detail="验证码发送失败，请稍后再试") from None
    if isinstance(exc, TooManyAttemptsError):
        raise HTTPException(status_code=429, detail="验证码错误次数过多，请重新获取") from None
    if isinstance(exc, codes.CodeRejectedError):
        raise HTTPException(status_code=400, detail="验证码错误或已过期") from None
    raise exc


def _normalized_phone(raw: str) -> str:
    """Normalize a phone number, turning failures into HTTP 422."""
    try:
        return normalize_phone(raw)
    except InvalidPhoneError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
        return UserResponse(
            id=user.id, email=user.email, phone=user.phone,
            username=user.username, token=token,
        )
    except HTTPException:
        raise
    except ValueError as ve:
        logger.exception("user_registration_validation_failed", error=str(ve))
        # Parse validation errors into user-friendly messages
        error_msg = str(ve)
        field = "password"
        code = "VALIDATION_ERROR"
        
        # 分支要与 validate_password_strength 抛出的文案一一对应，漏一个
        # 就会把英文原文直接吐给用户。
        if "letter" in error_msg.lower():
            message = "密码必须包含至少一个字母"
            code = "PASSWORD_NO_LETTER"
        elif "number" in error_msg.lower():
            message = "密码必须包含至少一个数字"
            code = "PASSWORD_NO_NUMBER"
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


@router.post("/apple", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["login"][0])
async def login_with_apple(request: Request, body: AppleLoginRequest):
    """Sign in with Apple 登录。.

    校验 iOS 端传来的 Apple 身份令牌，按邮箱查找或创建用户，签发本平台 JWT。
    Apple 用户无需密码：新建时写入随机不可用密码，后续始终经 Apple 验证登录。
    """
    try:
        try:
            claims = await verify_identity_token(body.identity_token)
        except AppleAuthError as e:
            raise HTTPException(
                status_code=401,
                detail={"message": str(e), "code": "APPLE_TOKEN_INVALID"},
            )

        apple_sub = claims["sub"]
        # Apple 可能返回私密转发邮箱；缺失时用 sub 兜底一个稳定的合成邮箱
        email = claims.get("email") or f"{apple_sub}@appleid.deepalpha.club"
        email = sanitize_email(email)

        user = await asyncio.to_thread(database_service.get_user_by_email, email)
        if user is None:
            # 生成随机强密码（含各类字符），仅用于占位，用户永远走 Apple 登录
            random_password = f"Aa1!{secrets.token_urlsafe(24)}"
            hashed_password = await asyncio.to_thread(User.hash_password, random_password)
            username = sanitize_string(body.full_name) if body.full_name else None
            user = await asyncio.to_thread(
                database_service.create_user, email, hashed_password, username
            )
            logger.info("apple_user_created", user_id=user.id)
        else:
            logger.info("apple_user_login", user_id=user.id)

        token = create_access_token(str(user.id))
        return TokenResponse(access_token=token.access_token, token_type="bearer", expires_at=token.expires_at)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("apple_login_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Apple 登录失败，请稍后再试")


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
            phone=user.phone,
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
            phone=updated_user.phone,
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
        
        if "letter" in error_msg.lower():
            message = "新密码必须包含至少一个字母"
        elif "number" in error_msg.lower():
            message = "新密码必须包含至少一个数字"
        elif "8 characters" in error_msg.lower() or "8位" in error_msg:
            message = "新密码长度至少需要 8 个字符"
        else:
            message = error_msg
        
        raise HTTPException(status_code=422, detail={"message": message, "code": "VALIDATION_ERROR"})
    except Exception as e:
        logger.exception("change_password_failed", user_id=user.id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to change password")


@router.delete("/me", response_model=dict)
async def delete_current_user(user: User = Depends(get_current_user)):
    """删除当前登录用户的账号（不可恢复）。.

    App Store 审核指南 5.1.1(v) 要求：支持账号创建的 App 必须提供账号删除入口。
    删除后该用户的登录凭证立即失效，关联会话一并清除。
    """
    try:
        # 按 id 删除：手机号注册的用户没有邮箱，按 email 删会漏掉他们。
        deleted = await asyncio.to_thread(database_service.delete_user_by_id, user.id)
        if not deleted:
            raise HTTPException(status_code=404, detail="用户不存在")

        logger.info("user_account_deleted", user_id=user.id)
        return {"message": "账号已删除"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("delete_user_failed", user_id=user.id, error=str(e))
        raise HTTPException(status_code=500, detail="删除账号失败，请稍后再试")


# ---------------------------------------------------------------------------
# 邮箱通道：验证码注册 + 找回密码
#
# 与文件上方那个 legacy 的 POST /register（无验证码）并存。legacy 端点保留是
# 因为已上架的旧版 App 仍在调用，待版本淘汰后再移除。新端点因此只能叫
# /register/verify——/register 这个路径被占了。
# ---------------------------------------------------------------------------


@router.post("/register/request-code")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chan_email_request_code"][0])
async def request_email_register_code(
    request: Request,
    payload: EmailCodeRequest,
    redis: Redis = Depends(get_redis),
):
    """Send a registration code to the given email.

    对「邮箱已注册」明确报错而不含糊：/register/verify 本身就必须在邮箱重复时
    报错，枚举面本来就存在，在这一步含糊只会让用户白等一封永远不会来的邮件。
    """
    try:
        email = sanitize_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = await asyncio.to_thread(database_service.get_user_by_email, email)
    if existing:
        raise HTTPException(status_code=400, detail="该邮箱已被注册，请直接登录")

    try:
        await codes.send_email_code(
            redis, Purpose.REGISTER, email, email_service.render_register
        )
    except Exception as exc:
        _raise_for_delivery(exc)

    logger.info("chan_register_code_sent")
    return {"sent": True}


@router.post("/register/verify", response_model=UserResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["register"][0])
async def register_with_email_code(
    request: Request,
    payload: EmailRegisterRequest,
    redis: Redis = Depends(get_redis),
):
    """Verify the email code and create the account.

    先验码再建号：邮箱填错时根本不该产生账号。
    """
    try:
        email = sanitize_email(payload.email)
        password = payload.password.get_secret_value()
        validate_password_strength(password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        await codes.verify_email_code(redis, Purpose.REGISTER, email, payload.code)
    except Exception as exc:
        _raise_for_delivery(exc)

    existing = await asyncio.to_thread(database_service.get_user_by_email, email)
    if existing:
        raise HTTPException(status_code=400, detail="该邮箱已被注册")

    username = sanitize_string(payload.username) if payload.username else None
    hashed = await asyncio.to_thread(User.hash_password, password)
    user = await asyncio.to_thread(
        database_service.create_user, email, hashed, username, None
    )

    token = create_access_token(str(user.id))
    logger.info("chan_user_registered_by_email", user_id=user.id)
    return UserResponse(
        id=user.id, email=user.email, phone=user.phone, username=user.username, token=token
    )


@router.post("/password-reset/request")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chan_email_request_code"][0])
async def request_email_password_reset(
    request: Request,
    payload: EmailCodeRequest,
    redis: Redis = Depends(get_redis),
):
    """Send a password-reset code to the given email.

    无论邮箱是否注册过都返回成功，避免这个接口变成「查某个邮箱有没有在本站
    注册」的探测器。与注册发码那条的取舍不同：注册流程后面必然会因重复而
    报错，这里没有这个约束。
    """
    try:
        email = sanitize_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = await asyncio.to_thread(database_service.get_user_by_email, email)
    if existing:
        try:
            await codes.send_email_code(
                redis, Purpose.PASSWORD_RESET, email, email_service.render_password_reset
            )
        except Exception as exc:
            _raise_for_delivery(exc)
        logger.info("chan_password_reset_code_sent")
    else:
        logger.info("chan_password_reset_requested_for_unknown_email")

    return {"sent": True}


@router.post("/password-reset/confirm")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chan_code_verify"][0])
async def confirm_email_password_reset(
    request: Request,
    payload: EmailPasswordResetConfirm,
    redis: Redis = Depends(get_redis),
):
    """Verify the email code and set a new password."""
    try:
        email = sanitize_email(payload.email)
        new_password = payload.new_password.get_secret_value()
        validate_password_strength(new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        await codes.verify_email_code(redis, Purpose.PASSWORD_RESET, email, payload.code)
    except Exception as exc:
        _raise_for_delivery(exc)

    user = await asyncio.to_thread(database_service.get_user_by_email, email)
    if user is None:
        # 走到这里说明码验过了但账号没了（并发删号）。不透露具体原因。
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    hashed = await asyncio.to_thread(User.hash_password, new_password)
    # 复用既有的 update_user，change_password 端点走的也是它，不要另加一个改密方法。
    await asyncio.to_thread(
        database_service.update_user, user_id=user.id, hashed_password=hashed
    )
    logger.info("chan_password_reset_done", user_id=user.id)
    return {"reset": True}


# ---------------------------------------------------------------------------
# 手机通道：与邮箱那套完全平行。
#
# 唯一的实质差别是验证码由阿里云生成保管核验，我们拿不到明文——这个不对称由
# 外部服务的形态决定，已经封装在 services/account/codes.py 里，路由层无感。
# ---------------------------------------------------------------------------


@router.post("/phone/register/request-code")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chan_phone_request_code"][0])
async def request_phone_register_code(
    request: Request,
    payload: PhoneCodeRequest,
    redis: Redis = Depends(get_redis),
):
    """Send a registration code to the given phone number."""
    phone = _normalized_phone(payload.phone)

    existing = await asyncio.to_thread(database_service.get_user_by_phone, phone)
    if existing:
        raise HTTPException(status_code=400, detail="该手机号已被注册，请直接登录")

    try:
        await codes.send_sms_code(redis, Purpose.PHONE_REGISTER, phone)
    except Exception as exc:
        _raise_for_delivery(exc)

    logger.info("chan_phone_register_code_sent")
    return {"sent": True}


@router.post("/phone/register", response_model=UserResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["register"][0])
async def register_with_phone_code(
    request: Request,
    payload: PhoneRegisterRequest,
    redis: Redis = Depends(get_redis),
):
    """Verify the SMS code and create the account.

    手机号注册的用户 email 为 None。
    """
    phone = _normalized_phone(payload.phone)
    try:
        password = payload.password.get_secret_value()
        validate_password_strength(password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        await codes.verify_sms_code(redis, Purpose.PHONE_REGISTER, phone, payload.code)
    except Exception as exc:
        _raise_for_delivery(exc)

    existing = await asyncio.to_thread(database_service.get_user_by_phone, phone)
    if existing:
        raise HTTPException(status_code=400, detail="该手机号已被注册")

    username = sanitize_string(payload.username) if payload.username else None
    hashed = await asyncio.to_thread(User.hash_password, password)
    user = await asyncio.to_thread(
        database_service.create_user, None, hashed, username, phone
    )

    token = create_access_token(str(user.id))
    logger.info("chan_user_registered_by_phone", user_id=user.id)
    return UserResponse(
        id=user.id, email=user.email, phone=user.phone, username=user.username, token=token
    )


@router.post("/phone/password-reset/request")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chan_phone_request_code"][0])
async def request_phone_password_reset(
    request: Request,
    payload: PhoneCodeRequest,
    redis: Redis = Depends(get_redis),
):
    """Send a password-reset code to the given phone number.

    号码是否注册过都返回成功，避免这个接口变成账号探测器。
    """
    phone = _normalized_phone(payload.phone)

    existing = await asyncio.to_thread(database_service.get_user_by_phone, phone)
    if existing:
        try:
            await codes.send_sms_code(redis, Purpose.PHONE_PASSWORD_RESET, phone)
        except Exception as exc:
            _raise_for_delivery(exc)
        logger.info("chan_phone_password_reset_code_sent")
    else:
        logger.info("chan_phone_password_reset_requested_for_unknown_phone")

    return {"sent": True}


@router.post("/phone/password-reset/confirm")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chan_code_verify"][0])
async def confirm_phone_password_reset(
    request: Request,
    payload: PhonePasswordResetConfirm,
    redis: Redis = Depends(get_redis),
):
    """Verify the SMS code and set a new password."""
    phone = _normalized_phone(payload.phone)
    try:
        new_password = payload.new_password.get_secret_value()
        validate_password_strength(new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        await codes.verify_sms_code(redis, Purpose.PHONE_PASSWORD_RESET, phone, payload.code)
    except Exception as exc:
        _raise_for_delivery(exc)

    user = await asyncio.to_thread(database_service.get_user_by_phone, phone)
    if user is None:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    hashed = await asyncio.to_thread(User.hash_password, new_password)
    # 复用既有的 update_user，change_password 端点走的也是它，不要另加一个改密方法。
    await asyncio.to_thread(
        database_service.update_user, user_id=user.id, hashed_password=hashed
    )
    logger.info("chan_phone_password_reset_done", user_id=user.id)
    return {"reset": True}


# ---------------------------------------------------------------------------
# 统一登录
#
# 与文件上方那个 Form 形态的 POST /login 并存。不改那一个而是新增，是因为它的
# 字段名是 email、内容类型是 form-urlencoded，已上架的旧版 App 和 Web 都在用；
# 同一路径同一方法也没法挂两个签名。
# ---------------------------------------------------------------------------


@router.post("/login/account", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["login"][0])
async def login_by_account(request: Request, payload: AccountLoginRequest):
    """Log in with either a phone number or an email address.

    类型由服务端判别，前端只给一个输入框。
    """
    try:
        kind, value = resolve_account(payload.account)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if kind is AccountKind.PHONE:
        user = await asyncio.to_thread(database_service.get_user_by_phone, value)
    else:
        user = await asyncio.to_thread(database_service.get_user_by_email, value)

    # 「账号不存在」和「密码错误」必须返回完全相同的响应，否则这个接口就是
    # 一个账号枚举器。
    password = payload.password.get_secret_value()
    if user is None or not await asyncio.to_thread(user.verify_password, password):
        logger.warning("chan_login_failed", kind=kind.value)
        raise HTTPException(
            status_code=401,
            detail={"message": "账号或密码错误", "code": "INVALID_CREDENTIALS"},
        )

    token = create_access_token(str(user.id))
    logger.info("chan_login_successful", user_id=user.id, kind=kind.value)
    return TokenResponse(
        access_token=token.access_token,
        token_type=token.token_type,
        expires_at=token.expires_at,
    )
