# app/api/v1/vocabulary/auth.py
"""WordLens 独立注册/登录路由（不复用主站 /auth）。

不用 `from __future__ import annotations`：slowapi 的 @limiter.limit() 装饰器会
让 FastAPI 把 body 参数的类型注解解析成未展开的 ForwardRef，body 会被误判成
query 参数，导致 422（这个文件的每个路由都挂了限流装饰器）。
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.client import get_redis
from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import logger
from app.db.session import get_db
from app.models.vocabulary import VocabularyUser
from app.schemas.vocabulary import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    RegisterCodeRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    VocabularyLoginRequest,
    VocabularyTokenResponse,
    VocabularyUserCreate,
    VocabularyUserResponse,
)
from app.services import email as email_service
from app.services.vocabulary import email_code
from app.services.vocabulary import users as user_service
from app.utils.auth import create_access_token
from app.utils.sanitization import sanitize_email, validate_vocabulary_password_strength

from .dependencies import get_current_vocab_user

router = APIRouter()


async def _issue_and_send(
    redis: Redis, purpose: email_code.Purpose, email: str, render
) -> None:
    """签发验证码并发信。失败时回滚，让用户可以立刻重试。"""
    try:
        code = await email_code.issue_code(redis, purpose, email)
    except email_code.ResendTooSoonError:
        raise HTTPException(
            status_code=429,
            detail=f"验证码已发送，请 {settings.EMAIL_CODE_RESEND_COOLDOWN} 秒后再试",
        ) from None

    subject, html, text = render(code, settings.EMAIL_CODE_TTL // 60)
    try:
        await email_service.send_email(email, subject, html, text)
    except email_service.EmailNotConfiguredError:
        # 邮件没发出去就不能留着冷却锁，否则用户被一次配置问题锁在门外 60 秒，
        # 而且那 60 秒里怎么点都没用。
        await email_code.discard_code(redis, purpose, email)
        logger.error("email_code_not_configured", purpose=purpose.value)
        raise HTTPException(status_code=503, detail="邮件服务暂不可用，请稍后再试") from None
    except email_service.EmailSendError:
        await email_code.discard_code(redis, purpose, email)
        raise HTTPException(status_code=502, detail="验证码发送失败，请稍后再试") from None


@router.post("/register/request-code")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["vocabulary_register_request_code"][0])
async def request_register_code(
    request: Request,
    payload: RegisterCodeRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """给待注册的邮箱发验证码。

    这里对「邮箱已注册」明确报错，而不像找回密码那样含糊其辞。看起来像账号枚举，
    但 /register 本身就必须在邮箱重复时报错（否则用户不知道为什么注册不了），
    枚举面本来就存在，在这一步含糊只会让用户白等一封永远不会来的邮件。
    """
    try:
        email = sanitize_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if await user_service.get_user_by_email(db, email) is not None:
        raise HTTPException(status_code=400, detail="该邮箱已被注册，请直接登录")

    await _issue_and_send(redis, email_code.Purpose.REGISTER, email, email_service.render_register)
    logger.info("register_code_sent")
    return {"sent": True}


@router.post("/register", response_model=VocabularyTokenResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["register"][0])
async def register(
    request: Request,
    payload: VocabularyUserCreate,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """校验邮箱验证码并创建账号。

    先验码再建号，而不是「先建号后验证」：邮箱填错时根本不该产生账号。否则
    数据库里会攒下一堆永远无法登录、也无法找回密码的僵尸账号，还白占了邮箱
    唯一索引——真正的主人以后想用这个邮箱注册都注册不了。
    """
    try:
        email = sanitize_email(payload.email)
        password = payload.password.get_secret_value()
        validate_vocabulary_password_strength(password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        ok = await email_code.verify_code(redis, email_code.Purpose.REGISTER, email, payload.code)
    except email_code.TooManyAttemptsError:
        raise HTTPException(
            status_code=429, detail="验证码错误次数过多，已失效，请重新获取"
        ) from None
    if not ok:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    # 验码通过后再查重：这中间的窗口极小，但同一邮箱并发注册时唯一索引会兜底。
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


@router.post("/password-reset/request")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["vocabulary_password_reset_request"][0])
async def request_password_reset(
    request: Request,
    payload: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """给邮箱发一个找回密码的验证码。

    无论邮箱是否注册过，都返回同样的成功响应。否则这个接口就成了「查某个邮箱
    有没有在本站注册」的探测器——这类账号枚举是拖库撞库的第一步。
    """
    try:
        email = sanitize_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    user = await user_service.get_user_by_email(db, email)
    if user is not None:
        await _issue_and_send(
            redis, email_code.Purpose.PASSWORD_RESET, email, email_service.render_password_reset
        )
        logger.info("password_reset_code_sent", user_id=str(user.id))
    else:
        logger.info("password_reset_requested_for_unknown_email")

    return {"sent": True}


@router.post("/password-reset/confirm")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["vocabulary_password_reset_confirm"][0])
async def confirm_password_reset(
    request: Request,
    payload: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """校验验证码并设置新密码。"""
    try:
        email = sanitize_email(payload.email)
        new_password = payload.new_password.get_secret_value()
        validate_vocabulary_password_strength(new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        ok = await email_code.verify_code(redis, email_code.Purpose.PASSWORD_RESET, email, payload.code)
    except email_code.TooManyAttemptsError:
        raise HTTPException(
            status_code=429, detail="验证码错误次数过多，已失效，请重新获取"
        ) from None
    if not ok:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    # 验证码是对邮箱所有权的证明，走到这里才去取用户。用户在这中间被删掉属于
    # 极端边角，按验证码无效处理即可。
    user = await user_service.get_user_by_email(db, email)
    if user is None:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    await user_service.change_password(db, user, new_password)
    logger.info("password_reset_completed", user_id=str(user.id))
    return {"reset": True}


@router.post("/delete-account")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["vocabulary_delete_account"][0])
async def delete_account(
    request: Request,
    payload: DeleteAccountRequest,
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """彻底删除当前账号及其全部数据，需校验密码。不可恢复。

    App Store 审核指南 5.1.1(v) 强制要求：有注册功能的 App 必须提供 App 内
    自助删除账号的入口。

    用 POST 而不是 `DELETE /me`：带 body 的 DELETE 在 RFC 9110 里语义未定义，
    部分代理会把 body 丢掉，而这里必须带密码做二次确认。同时也和已有的
    change-password 保持一致的调用风格。
    """
    if not user.verify_password(payload.password.get_secret_value()):
        raise HTTPException(status_code=401, detail="密码不正确")

    user_id = str(user.id)
    await user_service.delete_user(db, user.id)
    logger.info("vocabulary_user_deleted", user_id=user_id)
    return {"deleted": True}
