"""缠论验证码收发测试。

重点锁两件事：
1. 缠论的验证码落在 chan: 前缀下，与 WordLens 物理隔离
2. 发送失败时冷却必须回滚——否则一次配置故障会把用户锁在门外 60 秒
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services import email as email_service
from app.services.account import codes
from app.services.verification_code import Purpose

EMAIL = "someone@example.com"
PHONE = "+8613800138000"


def _redis() -> AsyncMock:
    r = AsyncMock()
    r.get.return_value = None
    r.exists.return_value = 0
    r.incr.return_value = 1
    return r


async def test_email_code_uses_chan_prefix():
    """缠论的验证码 key 必须落在 chan: 前缀下。"""
    redis = _redis()
    with patch.object(email_service, "send_email", AsyncMock()):
        await codes.send_email_code(redis, Purpose.REGISTER, EMAIL, email_service.render_register)

    keys = {c.args[0] for c in redis.set.await_args_list}
    assert keys and all(k.startswith("chan:vercode:") for k in keys)


async def test_email_code_is_sent_with_chan_brand():
    """邮件署名必须是缠论，不能是鹦鹉背单词。"""
    redis = _redis()
    send = AsyncMock()
    with patch.object(email_service, "send_email", send):
        await codes.send_email_code(redis, Purpose.REGISTER, EMAIL, email_service.render_register)

    assert send.await_count == 1
    subject = send.await_args.args[1]
    assert "DeepAlpha 缠论" in subject


async def test_cooldown_rolled_back_when_send_fails():
    """回归用例：邮件没发出去就不能留着冷却锁。"""
    redis = _redis()
    with patch.object(
        email_service, "send_email", AsyncMock(side_effect=email_service.EmailSendError)
    ):
        with pytest.raises(codes.CodeDeliveryError):
            await codes.send_email_code(
                redis, Purpose.REGISTER, EMAIL, email_service.render_register
            )

    deleted = {c.args[0] for c in redis.delete.await_args_list}
    assert any("cooldown" in k for k in deleted), "发信失败后没有解除冷却"


async def test_email_not_configured_raises_unavailable():
    """SMTP 未配置属于服务端问题，要和「发送失败」区分开。"""
    redis = _redis()
    with patch.object(
        email_service, "send_email", AsyncMock(side_effect=email_service.EmailNotConfiguredError)
    ):
        with pytest.raises(codes.CodeChannelUnavailableError):
            await codes.send_email_code(
                redis, Purpose.REGISTER, EMAIL, email_service.render_register
            )


async def test_sms_cooldown_only_starts_after_successful_send():
    """短信发失败不能上冷却，否则临时故障会变成 60 秒干等。"""
    from app.services import sms as sms_service

    redis = _redis()
    with patch.object(
        sms_service, "send_verification_code", AsyncMock(side_effect=sms_service.SMSSendError)
    ):
        with pytest.raises(codes.CodeDeliveryError):
            await codes.send_sms_code(redis, Purpose.PHONE_REGISTER, PHONE)

    cooldown_writes = [c for c in redis.set.await_args_list if "cooldown" in c.args[0]]
    assert not cooldown_writes, "短信没发成却上了冷却"


async def test_sms_blocked_when_phone_daily_limit_reached():
    """单号当日发送到上限后，直接拦下，不再调阿里云（省钱）。"""
    from app.core.config import settings
    from app.services import sms as sms_service

    redis = _redis()

    def _get(key: str):
        # 单号计数已达上限，其它 key（冷却/全站）当作不存在。
        return str(settings.SMS_PER_PHONE_DAILY_LIMIT) if "sms_daily" in key else None

    redis.get.side_effect = _get

    send = AsyncMock()
    with patch.object(sms_service, "send_verification_code", send):
        with pytest.raises(codes.DailySendLimitError):
            await codes.send_sms_code(redis, Purpose.PHONE_REGISTER, PHONE)

    assert send.await_count == 0, "超过单号上限还调了短信接口"


async def test_sms_rejects_non_china_number():
    """目前只支持中国大陆号，国际号在发送前就被拦下，不调阿里云。"""
    from app.services import sms as sms_service

    redis = _redis()
    send = AsyncMock()
    with patch.object(sms_service, "send_verification_code", send):
        with pytest.raises(codes.CountryNotSupportedError):
            await codes.send_sms_code(redis, Purpose.PHONE_REGISTER, "+14155552671")

    assert send.await_count == 0, "国际号不该真的发短信"


async def test_sms_counts_toward_quota_only_after_successful_send():
    """发送成功才计入单号当日配额。"""
    from app.services import sms as sms_service

    redis = _redis()  # get 恒返回 None → 未触限
    with patch.object(sms_service, "send_verification_code", AsyncMock()):
        await codes.send_sms_code(redis, Purpose.PHONE_REGISTER, PHONE)

    incr_keys = [c.args[0] for c in redis.incr.await_args_list]
    assert any("sms_daily" in k for k in incr_keys), "没有累计单号计数"


async def test_sms_verify_records_failed_attempt_on_wrong_code():
    """验错要计数，否则 6 位数字可以无限次猜。"""
    from app.services import sms as sms_service

    redis = _redis()
    with patch.object(sms_service, "check_verification_code", AsyncMock(return_value=False)):
        with pytest.raises(codes.CodeRejectedError):
            await codes.verify_sms_code(redis, Purpose.PHONE_REGISTER, PHONE, "000000")

    assert redis.incr.await_count == 1
