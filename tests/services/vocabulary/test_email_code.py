"""找回密码验证码的生成与校验逻辑测试。

安全上的几条硬要求，都用测试锁住：
1. Redis 里存的必须是哈希，不能是明文验证码
2. 错误次数用尽后验证码立即作废，不能靠等它自然过期
3. 校验成功后验证码一次性失效，不能复用
4. 冷却期内不能重复发送（防短时间轰炸用户邮箱）
"""

from unittest.mock import AsyncMock

import pytest

from app.services.vocabulary import email_code as ec

EMAIL = "someone@example.com"
PURPOSE = ec.Purpose.PASSWORD_RESET


def _redis() -> AsyncMock:
    r = AsyncMock()
    r.get.return_value = None
    r.exists.return_value = 0
    r.incr.return_value = 1
    return r


# ---------- 验证码生成 ----------


def test_generate_code_is_six_digits():
    for _ in range(50):
        code = ec.generate_code()
        assert len(code) == 6
        assert code.isdigit()


def test_generate_code_is_not_predictable():
    """用 secrets 而不是 random：50 次里不该出现大量重复。"""
    codes = {ec.generate_code() for _ in range(50)}
    assert len(codes) > 40


# ---------- 存储 ----------


async def test_issue_code_stores_hash_not_plaintext():
    redis = _redis()
    code = await ec.issue_code(redis, PURPOSE, EMAIL)

    stored = [c.args[1] for c in redis.set.await_args_list if "code" in c.args[0]]
    assert stored, "没有写入验证码"
    assert code not in stored, "Redis 里存了明文验证码"
    assert stored[0] == ec._hash_code(code)


async def test_issue_code_sets_ttl_on_every_key():
    """任何 key 都必须带 TTL，否则会永久占用 Redis。"""
    redis = _redis()
    await ec.issue_code(redis, PURPOSE, EMAIL)

    for call in redis.set.await_args_list:
        assert call.kwargs.get("ex"), f"key {call.args[0]} 没设过期时间"


async def test_issue_code_rejected_during_cooldown():
    redis = _redis()
    redis.exists.return_value = 1  # 冷却标记还在

    with pytest.raises(ec.ResendTooSoonError):
        await ec.issue_code(redis, PURPOSE, EMAIL)


# ---------- 校验 ----------


async def test_verify_accepts_correct_code():
    redis = _redis()
    code = "123456"
    redis.get.return_value = ec._hash_code(code)

    assert await ec.verify_code(redis, PURPOSE, EMAIL, code) is True


async def test_verify_rejects_wrong_code():
    redis = _redis()
    redis.get.return_value = ec._hash_code("123456")

    assert await ec.verify_code(redis, PURPOSE, EMAIL, "999999") is False


async def test_verify_returns_false_when_no_code_issued():
    redis = _redis()
    redis.get.return_value = None

    assert await ec.verify_code(redis, PURPOSE, EMAIL, "123456") is False


async def test_correct_code_is_consumed_after_use():
    """一次性：验证成功后立刻删掉，防止同一个码被重复使用。"""
    redis = _redis()
    code = "123456"
    redis.get.return_value = ec._hash_code(code)

    await ec.verify_code(redis, PURPOSE, EMAIL, code)

    deleted = [c.args[0] for c in redis.delete.await_args_list]
    assert any("code" in k for k in deleted), "验证成功后没有清除验证码"


async def test_code_invalidated_after_max_attempts():
    """错够次数直接作废，不给暴力枚举 6 位数字的机会。"""
    redis = _redis()
    redis.get.return_value = ec._hash_code("123456")
    redis.incr.return_value = ec.settings.EMAIL_CODE_MAX_ATTEMPTS

    with pytest.raises(ec.TooManyAttemptsError):
        await ec.verify_code(redis, PURPOSE, EMAIL, "000000")

    deleted = [c.args[0] for c in redis.delete.await_args_list]
    assert any("code" in k for k in deleted), "次数用尽后没有作废验证码"


# ---------- key 设计 ----------


async def test_keys_are_namespaced_and_do_not_leak_email():
    """Redis key 里不能出现明文邮箱：key 常被运维和监控看到。"""
    redis = _redis()
    await ec.issue_code(redis, PURPOSE, EMAIL)

    for call in redis.set.await_args_list:
        key = call.args[0]
        assert key.startswith("vocab:emailcode:")
        assert EMAIL not in key


# ---------- 发信失败的回滚 ----------


async def test_discard_code_also_clears_cooldown():
    """发信失败时必须连冷却一起解除。

    回归用例：上线首测时发现，SMTP 未配置导致 503，但冷却锁已经先上了，
    用户被一次配置问题锁在门外 60 秒，期间怎么点都没用。既然邮件没发出去，
    就该当这次请求没发生过。
    """
    redis = _redis()
    await ec.discard_code(redis, PURPOSE, EMAIL)

    deleted = [c.args[0] for c in redis.delete.await_args_list]
    assert any("cooldown" in k for k in deleted), "没有解除冷却"
    assert any("code" in k for k in deleted), "没有作废验证码"
    assert any("attempts" in k for k in deleted), "没有清除错误计数"


# ---------- 用途隔离 ----------


async def test_purposes_use_separate_keys():
    """注册和找回密码的验证码必须互不通用。

    否则会出现这种攻击：用受害者邮箱走一遍「注册」流程，如果对方邮箱恰好能被
    看到（共用设备、邮件预览、转发规则），拿到的注册码就能直接去重置密码。
    命名空间隔离让两者物理上不可能撞上。
    """
    redis = _redis()
    await ec.issue_code(redis, ec.Purpose.REGISTER, EMAIL)
    reg_keys = {c.args[0] for c in redis.set.await_args_list}

    redis2 = _redis()
    await ec.issue_code(redis2, ec.Purpose.PASSWORD_RESET, EMAIL)
    reset_keys = {c.args[0] for c in redis2.set.await_args_list}

    assert not (reg_keys & reset_keys), "两种用途的 key 有重叠"
    assert all("register" in k for k in reg_keys)
    assert all("pwreset" in k for k in reset_keys)


async def test_code_issued_for_register_fails_password_reset_verification():
    """拿注册码去验证找回密码，必须失败。"""
    redis = _redis()
    code = "123456"
    # 只有 REGISTER 命名空间下有码；查 PASSWORD_RESET 时 get 返回 None
    redis.get.return_value = None

    assert await ec.verify_code(redis, ec.Purpose.PASSWORD_RESET, EMAIL, code) is False
