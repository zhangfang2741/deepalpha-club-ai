"""共享验证码模块测试。

vocabulary 侧的行为已由 tests/services/vocabulary/test_verification_code.py 锁住，
这里只测提升为共享模块后新增的能力：前缀隔离。两个 App 用同一个手机号时，
各自的验证码必须落在不同的 Redis key 上——否则 A 应用发的码能用来注册 B 应用。
"""

from unittest.mock import AsyncMock

import pytest

from app.services.verification_code import (
    CodeStore,
    Purpose,
    ResendTooSoonError,
    TooManyAttemptsError,
    generate_code,
)

IDENTIFIER = "+8613800138000"


def _redis() -> AsyncMock:
    r = AsyncMock()
    r.get.return_value = None
    r.exists.return_value = 0
    r.incr.return_value = 1
    return r


async def test_different_prefixes_produce_disjoint_keys():
    """同一手机号、同一用途，两个 store 的 key 不能有任何重叠。"""
    chan = CodeStore("chan:vercode")
    vocab = CodeStore("vocab:vercode")

    r1 = _redis()
    await chan.issue_code(r1, Purpose.PHONE_REGISTER, IDENTIFIER)
    chan_keys = {c.args[0] for c in r1.set.await_args_list}

    r2 = _redis()
    await vocab.issue_code(r2, Purpose.PHONE_REGISTER, IDENTIFIER)
    vocab_keys = {c.args[0] for c in r2.set.await_args_list}

    assert not (chan_keys & vocab_keys)
    assert all(k.startswith("chan:vercode:") for k in chan_keys)
    assert all(k.startswith("vocab:vercode:") for k in vocab_keys)


async def test_code_from_other_app_does_not_verify():
    """WordLens 签发的码拿到缠论来验，必须失败。"""
    chan = CodeStore("chan:vercode")
    redis = _redis()
    redis.get.return_value = None  # chan 命名空间下没有码

    assert await chan.verify_code(redis, Purpose.PHONE_REGISTER, IDENTIFIER, "123456") is False


async def test_keys_never_contain_plaintext_identifier():
    """Redis key 里不能出现明文手机号：key 常被运维和监控看到。"""
    chan = CodeStore("chan:vercode")
    redis = _redis()
    await chan.issue_code(redis, Purpose.REGISTER, IDENTIFIER)

    for call in redis.set.await_args_list:
        assert IDENTIFIER not in call.args[0]


async def test_every_key_has_ttl():
    """任何 key 都必须带 TTL，否则会永久占用 Redis。"""
    chan = CodeStore("chan:vercode")
    redis = _redis()
    await chan.issue_code(redis, Purpose.REGISTER, IDENTIFIER)

    for call in redis.set.await_args_list:
        assert call.kwargs.get("ex"), f"key {call.args[0]} 没设过期时间"


async def test_cooldown_blocks_reissue():
    """冷却期内不能重复发送，防短时间轰炸用户。"""
    chan = CodeStore("chan:vercode")
    redis = _redis()
    redis.exists.return_value = 1

    with pytest.raises(ResendTooSoonError):
        await chan.issue_code(redis, Purpose.REGISTER, IDENTIFIER)


async def test_max_attempts_invalidates_code():
    """错够次数直接作废，不给暴力枚举 6 位数字的机会。"""
    from app.core.config import settings

    chan = CodeStore("chan:vercode")
    redis = _redis()
    redis.get.return_value = chan._hash_code("123456")
    redis.incr.return_value = settings.EMAIL_CODE_MAX_ATTEMPTS

    with pytest.raises(TooManyAttemptsError):
        await chan.verify_code(redis, Purpose.REGISTER, IDENTIFIER, "000000")


def test_generate_code_is_six_digits():
    """验证码必须是 6 位纯数字。"""
    for _ in range(50):
        code = generate_code()
        assert len(code) == 6 and code.isdigit()
