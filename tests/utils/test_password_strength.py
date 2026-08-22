"""主站密码强度规则测试。

规则：至少 8 位，含字母和数字。不再要求大小写区分和特殊字符——原来那套
（8 位 + 大写 + 小写 + 数字 + 特殊字符）对普通用户太苛刻，实际效果是逼着
用户去用 `Password1!` 这种既难记又没多少熵的密码。

这里同时锁住「三处实现必须一致」：sanitization 里的函数是唯一实现，
schemas 里的两个 validator 都委托给它，不能各写一份。
"""

import pytest

from app.schemas.auth import PasswordChange, UserCreate
from app.utils.sanitization import validate_password_strength

VALID = ["abcd1234", "Password1", "a1b2c3d4", "letmein123", "ABCD1234"]
INVALID = [
    "abcdefgh",   # 没有数字
    "12345678",   # 没有字母
    "abc123",     # 不足 8 位
    "",           # 空
]


@pytest.mark.parametrize("password", VALID)
def test_accepts_letters_plus_digits(password):
    """字母 + 数字 + 至少 8 位就应该通过。"""
    assert validate_password_strength(password) is True


@pytest.mark.parametrize("password", INVALID)
def test_rejects_missing_requirements(password):
    """缺字母、缺数字或长度不足都要拒绝。"""
    with pytest.raises(ValueError):
        validate_password_strength(password)


def test_no_longer_requires_special_character():
    """回归用例：纯字母数字的密码不能再被特殊字符规则拦下。"""
    assert validate_password_strength("abcd1234") is True


def test_no_longer_requires_mixed_case():
    """回归用例：全小写和全大写都应该通过。"""
    assert validate_password_strength("abcd1234") is True
    assert validate_password_strength("ABCD1234") is True


# ---------- 三处实现必须一致 ----------


def test_user_create_schema_accepts_same_passwords():
    """UserCreate 的 validator 不能比 validate_password_strength 更严。"""
    for password in VALID:
        UserCreate(email="someone@example.com", password=password)


def test_user_create_schema_rejects_same_passwords():
    for password in ["abcdefgh", "12345678"]:
        with pytest.raises(ValueError):
            UserCreate(email="someone@example.com", password=password)


def test_password_change_schema_accepts_same_passwords():
    """PasswordChange 的 validator 同样不能更严。"""
    for password in VALID:
        PasswordChange(current_password="whatever", new_password=password)


def test_password_change_schema_rejects_same_passwords():
    for password in ["abcdefgh", "12345678"]:
        with pytest.raises(ValueError):
            PasswordChange(current_password="whatever", new_password=password)
