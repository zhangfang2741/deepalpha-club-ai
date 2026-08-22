"""统一登录的账号判别测试。

登录框只有一个，用户可能输手机号也可能输邮箱，服务端得自己认出来。
判别错了的后果是查错表，用户会看到「账号或密码错误」而不知道为什么。
"""

import pytest

from app.services.account.accounts import AccountKind, resolve_account


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("13800138000", "+8613800138000"),
        ("+8613800138000", "+8613800138000"),
        ("138 0013 8000", "+8613800138000"),
        ("138-0013-8000", "+8613800138000"),
        ("８６１３８００１３８０００", "+8613800138000"),  # 全角输入
    ],
)
def test_recognizes_phone_and_normalizes(raw, expected):
    """各种写法的手机号都要归一化成 E.164。"""
    kind, value = resolve_account(raw)
    assert kind is AccountKind.PHONE
    assert value == expected


@pytest.mark.parametrize(
    "raw",
    ["someone@example.com", "Someone@Example.COM", "  someone@example.com  "],
)
def test_recognizes_email_and_normalizes(raw):
    """邮箱统一转小写去空白。"""
    kind, value = resolve_account(raw)
    assert kind is AccountKind.EMAIL
    assert value == "someone@example.com"


@pytest.mark.parametrize("raw", ["", "   ", "12345", "not-an-account", "12345678901234567890"])
def test_rejects_garbage(raw):
    """两种格式都不满足的输入必须报错，而不是默默当成邮箱去查库。"""
    with pytest.raises(ValueError):
        resolve_account(raw)


def test_digits_that_are_not_valid_cn_mobile_are_rejected():
    """11 位但号段非法（1 后面不是 3-9），不该被当成手机号也不该当成邮箱。"""
    with pytest.raises(ValueError):
        resolve_account("12800138000")
