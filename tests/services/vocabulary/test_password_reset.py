"""找回密码验证码的生成与校验逻辑测试。

安全上的几条硬要求，都用测试锁住：
1. Redis 里存的必须是哈希，不能是明文验证码
2. 错误次数用尽后验证码立即作废，不能靠等它自然过期
3. 校验成功后验证码一次性失效，不能复用
4. 冷却期内不能重复发送（防短时间轰炸用户邮箱）
"""

from unittest.mock import AsyncMock

import pytest

from app.services.vocabulary import password_reset as pr

EMAIL = "someone@example.com"


def _redis() -> AsyncMock:
    r = AsyncMock()
    r.get.return_value = None
    r.exists.return_value = 0
    r.incr.return_value = 1
    return r


# ---------- 验证码生成 ----------


def test_generate_code_is_six_digits():
    for _ in range(50):
        code = pr.generate_code()
        assert len(code) == 6
        assert code.isdigit()


def test_generate_code_is_not_predictable():
    """用 secrets 而不是 random：50 次里不该出现大量重复。"""
    codes = {pr.generate_code() for _ in range(50)}
    assert len(codes) > 40


# ---------- 存储 ----------


async def test_issue_code_stores_hash_not_plaintext():
    redis = _redis()
    code = await pr.issue_code(redis, EMAIL)

    stored = [c.args[1] for c in redis.set.await_args_list if "code" in c.args[0]]
    assert stored, "没有写入验证码"
    assert code not in stored, "Redis 里存了明文验证码"
    assert stored[0] == pr._hash_code(code)


async def test_issue_code_sets_ttl_on_every_key():
    """任何 key 都必须带 TTL，否则会永久占用 Redis。"""
    redis = _redis()
    await pr.issue_code(redis, EMAIL)

    for call in redis.set.await_args_list:
        assert call.kwargs.get("ex"), f"key {call.args[0]} 没设过期时间"


async def test_issue_code_rejected_during_cooldown():
    redis = _redis()
    redis.exists.return_value = 1  # 冷却标记还在

    with pytest.raises(pr.ResendTooSoonError):
        await pr.issue_code(redis, EMAIL)


# ---------- 校验 ----------


async def test_verify_accepts_correct_code():
    redis = _redis()
    code = "123456"
    redis.get.return_value = pr._hash_code(code)

    assert await pr.verify_code(redis, EMAIL, code) is True


async def test_verify_rejects_wrong_code():
    redis = _redis()
    redis.get.return_value = pr._hash_code("123456")

    assert await pr.verify_code(redis, EMAIL, "999999") is False


async def test_verify_returns_false_when_no_code_issued():
    redis = _redis()
    redis.get.return_value = None

    assert await pr.verify_code(redis, EMAIL, "123456") is False


async def test_correct_code_is_consumed_after_use():
    """一次性：验证成功后立刻删掉，防止同一个码被重复使用。"""
    redis = _redis()
    code = "123456"
    redis.get.return_value = pr._hash_code(code)

    await pr.verify_code(redis, EMAIL, code)

    deleted = [c.args[0] for c in redis.delete.await_args_list]
    assert any("code" in k for k in deleted), "验证成功后没有清除验证码"


async def test_code_invalidated_after_max_attempts():
    """错够次数直接作废，不给暴力枚举 6 位数字的机会。"""
    redis = _redis()
    redis.get.return_value = pr._hash_code("123456")
    redis.incr.return_value = pr.settings.PASSWORD_RESET_MAX_ATTEMPTS

    with pytest.raises(pr.TooManyAttemptsError):
        await pr.verify_code(redis, EMAIL, "000000")

    deleted = [c.args[0] for c in redis.delete.await_args_list]
    assert any("code" in k for k in deleted), "次数用尽后没有作废验证码"


# ---------- key 设计 ----------


async def test_keys_are_namespaced_and_do_not_leak_email():
    """Redis key 里不能出现明文邮箱：key 常被运维和监控看到。"""
    redis = _redis()
    await pr.issue_code(redis, EMAIL)

    for call in redis.set.await_args_list:
        key = call.args[0]
        assert key.startswith("vocab:pwreset:")
        assert EMAIL not in key
