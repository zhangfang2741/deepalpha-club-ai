"""手机号归一化。

统一存 E.164（+国家码+号码）。同一个号码用户可能写成 13800138000、
+86 138-0013-8000、086-13800138000 等多种形式，不归一化会有两个后果：
库里注册出多个账号，以及「换个写法就能绕过已注册检查」。

不引 phonenumbers 库：它有 2MB 的全球号码元数据，而这里只需要支持中国大陆号
加上「显式带国家码的国际号原样保留」。真要做全球号码校验时再换不迟。
"""
from __future__ import annotations

import re

from app.core.config import settings


class InvalidPhoneError(ValueError):
    """手机号格式不合法。"""


# 中国大陆手机号：1 开头，第二位 3-9，共 11 位。
_CN_MOBILE = re.compile(r"^1[3-9]\d{9}$")
# E.164 上限 15 位数字，国家码至少 1 位。
_E164 = re.compile(r"^\+[1-9]\d{6,14}$")


def _to_halfwidth(text: str) -> str:
    """全角数字转半角。中文输入法下很容易打出全角，肉眼几乎看不出区别。"""
    return "".join(
        chr(ord(ch) - 0xFEE0) if "０" <= ch <= "９" else ch for ch in text
    )


def normalize_phone(raw: str) -> str:
    """把各种写法的手机号归一化成 E.164。

    Raises:
        InvalidPhoneError: 格式不合法。
    """
    if not raw:
        raise InvalidPhoneError("请输入手机号")

    text = _to_halfwidth(raw).strip()
    # 分隔符（空格、连字符、括号）一律去掉，只保留可能的前导 + 和数字。
    text = re.sub(r"[\s\-()]", "", text)

    # 加号只允许出现在开头且只能有一个。不校验就用 re.sub 清洗的话，
    # "++8613800138000" 这种明显畸形的输入会被静默修正成合法号码。
    if "+" in text and (text.count("+") > 1 or not text.startswith("+")):
        raise InvalidPhoneError("手机号格式不正确")

    if text.startswith("+"):
        candidate = "+" + text[1:]
    elif text.startswith("00"):
        # 00 是国际直拨前缀，等价于 +
        candidate = "+" + text[2:]
    elif text.startswith("086") and _CN_MOBILE.match(text[3:]):
        # 「086-13800138000」严格说不规范（国际前缀是 00 不是 0），但国内用户
        # 写得很多，且 0 + 86 + 合法手机号没有别的解释，按 +86 处理。
        candidate = "+" + text[1:]
    else:
        digits = text
        if not digits.isdigit():
            raise InvalidPhoneError("手机号格式不正确")
        if _CN_MOBILE.match(digits):
            candidate = f"+{settings.DEFAULT_PHONE_COUNTRY_CODE}{digits}"
        elif digits.startswith("86") and _CN_MOBILE.match(digits[2:]):
            # 用户写了 8613800138000 这种不带 + 的形式
            candidate = f"+{digits}"
        else:
            raise InvalidPhoneError("手机号格式不正确")

    if not _E164.match(candidate):
        raise InvalidPhoneError("手机号格式不正确")

    # 国内号再走一遍号段校验：+86 后面必须是合法的 11 位手机号，
    # 否则 +8612345 这种也会因为满足 E.164 而蒙混过关。
    if candidate.startswith("+86") and not _CN_MOBILE.match(candidate[3:]):
        raise InvalidPhoneError("手机号格式不正确")

    return candidate


def to_aliyun_format(e164: str) -> str:
    """E.164 → 阿里云 SendSms 要求的 PhoneNumbers 格式。

    阿里云对两类号码要求不同：国内号要 11 位裸号（带 +86 会被拒），
    国际号要 00 开头而不是 +。
    """
    if e164.startswith("+86"):
        return e164[3:]
    return "00" + e164.lstrip("+")


def mask_phone(e164: str) -> str:
    """打码后的手机号，用于返回给前端展示（如「验证码已发送至 138****8000」）。"""
    digits = e164.lstrip("+")
    if len(digits) < 7:
        return "*" * len(digits)
    return f"{digits[:-8]}{digits[-8:-4].replace(digits[-8:-4], '****')}{digits[-4:]}"
