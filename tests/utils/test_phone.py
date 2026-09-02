"""手机号归一化测试。

归一化是这块最容易出错、后果又最实在的一环：同一个号码用户可能写成
13800138000、+86 138-0013-8000、086-13800138000……不统一就会在库里注册出
多个账号，而且「换个写法就能绕过已注册检查」。
"""

import pytest

from app.utils.phone import (
    InvalidPhoneError,
    is_domestic,
    normalize_phone,
    split_e164,
    to_aliyun_format,
)


class TestNormalize:
    """统一归一化到 E.164（+国家码+号码）。"""

    @pytest.mark.parametrize(
        "raw",
        [
            "13800138000",
            "+8613800138000",
            "8613800138000",
            "+86 138 0013 8000",
            "138-0013-8000",
            "+86-138-0013-8000",
            "  13800138000  ",
            "086 13800138000",
        ],
    )
    def test_all_common_forms_map_to_same_e164(self, raw: str):
        assert normalize_phone(raw) == "+8613800138000"

    def test_keeps_explicit_non_china_country_code(self):
        assert normalize_phone("+14155552671") == "+14155552671"
        assert normalize_phone("+442071838750") == "+442071838750"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("+1 415 555 2671", "+14155552671"),      # 美国
            ("+1 (415) 555-2671", "+14155552671"),    # 美国带括号写法
            ("0014155552671", "+14155552671"),        # 00 国际前缀等价于 +
            ("+852 9123 4567", "+85291234567"),       # 香港
            ("+65 8123 4567", "+6581234567"),         # 新加坡
            ("+81 90 1234 5678", "+819012345678"),    # 日本
        ],
    )
    def test_international_numbers(self, raw: str, expected: str):
        assert normalize_phone(raw) == expected

    def test_full_width_digits_are_converted(self):
        """中文输入法下很容易打出全角数字，肉眼看不出区别。"""
        assert normalize_phone("１３８００１３８０００") == "+8613800138000"


class TestReject:
    """不合法的输入必须明确拒绝，不能悄悄存进库里。"""

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            "1380013800",       # 少一位
            "138001380000",     # 多一位
            "12800138000",      # 国内号第二位不可能是 2
            "03800138000",      # 不以 1 开头
            "abcdefghijk",
            "+86",
            "++8613800138000",
            "+11",              # 带国家码但号段不存在
            "+9999999999999",   # 无此国家码
        ],
    )
    def test_rejects_invalid(self, raw: str):
        with pytest.raises(InvalidPhoneError):
            normalize_phone(raw)


class TestSplitE164:
    """阿里云要求国家码和国内号分开传。"""

    def test_china_number(self):
        assert split_e164("+8613800138000") == ("86", "13800138000")

    def test_us_number(self):
        assert split_e164("+14155552671") == ("1", "4155552671")

    def test_uk_number(self):
        assert split_e164("+442071838750") == ("44", "2071838750")

    def test_hong_kong_number(self):
        assert split_e164("+85291234567") == ("852", "91234567")


class TestIsDomestic:
    """按国内/国际分流短信模板。"""

    def test_china_is_domestic(self):
        assert is_domestic("+8613800138000") is True

    def test_us_is_not_domestic(self):
        assert is_domestic("+14155552671") is False


class TestAliyunFormat:
    """to_aliyun_format 仅 WordLens 在用，缠论已改走 split_e164。"""

    def test_china_number_strips_country_code(self):
        assert to_aliyun_format("+8613800138000") == "13800138000"

    def test_international_number_uses_00_prefix(self):
        assert to_aliyun_format("+14155552671") == "0014155552671"
