"""缠论 App 的验证码收发。

按渠道分工：邮箱的码由本地 CodeStore 生成保管（存哈希），经 SMTP 送达；
手机的码由阿里云号码认证服务生成保管核验，本地只留冷却和错误计数。
这个不对称是外部服务的形态决定的，不是设计选择——阿里云不把明文交给我们。

抛的是本模块自己的异常而不是 HTTPException：服务层不该知道 HTTP 状态码，
路由层负责翻译。
"""
from __future__ import annotations

from collections.abc import Callable

from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import logger
from app.services import email as email_service
from app.services import sms as sms_service
from app.services.verification_code import (
    CodeStore,
    Purpose,
    ResendTooSoonError,
    TooManyAttemptsError,
)
from app.utils.phone import to_aliyun_format

# 与 WordLens 的 vocab:vercode 物理隔离：同一个手机号在两个 App 里各有各的码。
store = CodeStore("chan:vercode")


class CodeDeliveryError(Exception):
    """验证码没能送达（发送失败）。"""


class CodeChannelUnavailableError(Exception):
    """渠道未配置，服务端问题。"""


class CodeRejectedError(Exception):
    """验证码错误或已过期。"""


# 用途 → 阿里云系统模板。注册用「登录/注册」模板，重置密码用「重置密码」模板，
# 文案会写明用户正在做什么。
_SMS_TEMPLATES = {
    Purpose.PHONE_REGISTER: lambda: settings.ALIYUN_SMS_TEMPLATE_REGISTER,
    Purpose.PHONE_PASSWORD_RESET: lambda: settings.ALIYUN_SMS_TEMPLATE_PASSWORD_RESET,
}


async def send_email_code(
    redis: Redis,
    purpose: Purpose,
    email: str,
    render: Callable[[str, int, str], tuple[str, str, str]],
) -> None:
    """签发验证码并发邮件。

    Raises:
        ResendTooSoonError: 还在冷却期。
        CodeChannelUnavailableError: SMTP 未配置。
        CodeDeliveryError: 发信失败。
    """
    code = await store.issue_code(redis, purpose, email)

    subject, html, text = render(code, settings.EMAIL_CODE_TTL // 60, settings.CHAN_BRAND_NAME)
    try:
        await email_service.send_email(
            email, subject, html, text, from_name=settings.CHAN_BRAND_NAME
        )
    except email_service.EmailNotConfiguredError:
        # 没发出去就不能留着冷却锁，否则用户被一次配置问题锁在门外 60 秒。
        await store.discard_code(redis, purpose, email)
        logger.error("chan_email_code_not_configured", purpose=purpose.value)
        raise CodeChannelUnavailableError from None
    except email_service.EmailSendError:
        await store.discard_code(redis, purpose, email)
        raise CodeDeliveryError from None


async def verify_email_code(redis: Redis, purpose: Purpose, email: str, code: str) -> None:
    """校验邮箱验证码。

    Raises:
        TooManyAttemptsError: 错误次数用尽。
        CodeRejectedError: 验证码错误或已过期。
    """
    if not await store.verify_code(redis, purpose, email, code):
        raise CodeRejectedError


async def send_sms_code(redis: Redis, purpose: Purpose, phone: str) -> None:
    """让阿里云发一条验证码短信。

    Raises:
        ResendTooSoonError: 还在冷却期。
        CodeChannelUnavailableError: 短信未配置。
        CodeDeliveryError: 发送失败。
    """
    if await store.is_cooling_down(redis, purpose, phone):
        raise ResendTooSoonError

    try:
        await sms_service.send_verification_code(
            to_aliyun_format(phone), _SMS_TEMPLATES[purpose]()
        )
    except sms_service.SMSNotConfiguredError:
        logger.error("chan_sms_not_configured", purpose=purpose.value)
        raise CodeChannelUnavailableError from None
    except sms_service.SMSResendTooSoonError:
        raise ResendTooSoonError from None
    except sms_service.SMSSendError:
        raise CodeDeliveryError from None

    # 发成功才上冷却和重置错误计数——发失败还锁着用户，会把一次临时故障
    # 变成 60 秒的干等（这个坑在邮件链路上真踩过一次）。
    await store.start_cooldown(redis, purpose, phone)


async def verify_sms_code(redis: Redis, purpose: Purpose, phone: str, code: str) -> None:
    """核验短信验证码。

    Raises:
        TooManyAttemptsError: 错误次数用尽。
        CodeChannelUnavailableError: 短信未配置。
        CodeDeliveryError: 校验调用失败。
        CodeRejectedError: 验证码错误或已过期。
    """
    # 阿里云不暴露「错几次就作废」，本地补一个计数器：6 位数字只有 100 万种可能，
    # 有效期内不限次数猜是能撞开的，而每次猜只是一次廉价的 API 调用。
    await store.assert_attempts_left(redis, purpose, phone)

    try:
        passed = await sms_service.check_verification_code(to_aliyun_format(phone), code)
    except sms_service.SMSNotConfiguredError:
        raise CodeChannelUnavailableError from None
    except sms_service.SMSCodeInvalidError:
        # 码不存在/已过期，与「码不对」走同一路径：对用户来说没有区别。
        passed = False
    except sms_service.SMSSendError:
        raise CodeDeliveryError from None

    if not passed:
        await store.record_failed_attempt(redis, purpose, phone)
        raise CodeRejectedError

    await store.clear_attempts(redis, purpose, phone)


__all__ = [
    "CodeChannelUnavailableError",
    "CodeDeliveryError",
    "CodeRejectedError",
    "Purpose",
    "ResendTooSoonError",
    "TooManyAttemptsError",
    "send_email_code",
    "send_sms_code",
    "store",
    "verify_email_code",
    "verify_sms_code",
]
