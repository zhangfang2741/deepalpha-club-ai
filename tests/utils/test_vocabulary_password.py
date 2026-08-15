"""WordLens 密码强度规则单元测试。

刻意只校验长度、不做字符组合要求（NIST SP 800-63B 建议废弃组合规则）。
这组用例锁住「不能偷偷把组合要求加回来」——加回去会直接抬高注册流失。
"""

import pytest

from app.utils.sanitization import (
    VOCABULARY_PASSWORD_MIN_LENGTH,
    validate_vocabulary_password_strength,
)


def test_min_length_is_six():
    assert VOCABULARY_PASSWORD_MIN_LENGTH == 6


@pytest.mark.parametrize(
    "password",
    [
        "abcdef",            # 纯字母
        "123456",            # 纯数字
        "!@#$%^",            # 纯符号
        "苹果香蕉橘子",         # 纯中文
        "a1!Bc2",            # 混合
        "x" * 64,            # 长密码
    ],
)
def test_accepts_any_composition_at_or_above_min_length(password: str):
    """只要够长就通过，不限制字符构成。"""
    assert validate_vocabulary_password_strength(password) is True


@pytest.mark.parametrize("password", ["", "a", "abcde", "12345"])
def test_rejects_too_short(password: str):
    with pytest.raises(ValueError, match="至少需要 6 个字符"):
        validate_vocabulary_password_strength(password)


def test_no_letter_requirement():
    """回归：曾要求必须含英文字母，已按 NIST 建议移除。"""
    assert validate_vocabulary_password_strength("135790") is True


def test_no_digit_requirement():
    """回归：曾要求必须含数字，已按 NIST 建议移除。"""
    assert validate_vocabulary_password_strength("password") is True
