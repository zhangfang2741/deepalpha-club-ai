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


async def test_sms_verify_records_failed_attempt_on_wrong_code():
    """验错要计数，否则 6 位数字可以无限次猜。"""
    from app.services import sms as sms_service

    redis = _redis()
    with patch.object(sms_service, "check_verification_code", AsyncMock(return_value=False)):
        with pytest.raises(codes.CodeRejectedError):
            await codes.verify_sms_code(redis, Purpose.PHONE_REGISTER, PHONE, "000000")

    assert redis.incr.await_count == 1
