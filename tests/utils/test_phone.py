"""手机号归一化测试。

归一化是这块最容易出错、后果又最实在的一环：同一个号码用户可能写成
13800138000、+86 138-0013-8000、086-13800138000……不统一就会在库里注册出
多个账号，而且「换个写法就能绕过已注册检查」。
"""

import pytest

from app.utils.phone import InvalidPhoneError, normalize_phone, to_aliyun_format


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
        ],
    )
    def test_rejects_invalid(self, raw: str):
        with pytest.raises(InvalidPhoneError):
            normalize_phone(raw)


class TestAliyunFormat:
    """阿里云对国内号和国际号要求的格式不同。"""

    def test_china_number_strips_country_code(self):
        """国内号阿里云要 11 位裸号，带 +86 会被拒。"""
        assert to_aliyun_format("+8613800138000") == "13800138000"

    def test_international_number_uses_00_prefix(self):
        """国际号阿里云要求 00 开头，不是 +。"""
        assert to_aliyun_format("+14155552671") == "0014155552671"
