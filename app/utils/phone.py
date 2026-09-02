"""手机号归一化与国家码拆分。

统一存 E.164（+国家码+号码）。同一个号码用户可能写成 13800138000、
+86 138-0013-8000、086-13800138000 等多种形式，不归一化会有两个后果：
库里注册出多个账号，以及「换个写法就能绕过已注册检查」。

多国支持：国际号码的号段规则（长度、前缀）各国不同，手写正则维护不了，改用
`phonenumbers`（Google libphonenumber 的 Python 移植）做权威校验。中国大陆的
若干便捷写法（裸 11 位、全角数字、086 前缀）在进 phonenumbers 之前先本地归一，
既保留老版本 App「只填 11 位」的向后兼容，也省掉 default_region 的猜测。
"""
from __future__ import annotations

import re

import phonenumbers

from app.core.config import settings


class InvalidPhoneError(ValueError):
    """手机号格式不合法。"""


# 中国大陆手机号：1 开头，第二位 3-9，共 11 位。
_CN_MOBILE = re.compile(r"^1[3-9]\d{9}$")


def _to_halfwidth(text: str) -> str:
    """全角数字转半角。中文输入法下很容易打出全角，肉眼几乎看不出区别。"""
    return "".join(
        chr(ord(ch) - 0xFEE0) if "０" <= ch <= "９" else ch for ch in text
    )


def _to_e164_candidate(raw: str) -> str:
    """把各种写法清洗成一个「带 + 的候选 E.164 串」，交给 phonenumbers 做权威校验。

    只负责补出国家码前缀，不做号段合法性判断——那是 phonenumbers 的职责。
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
        return text
    if text.startswith("00"):
        # 00 是国际直拨前缀，等价于 +
        return "+" + text[2:]
    if text.startswith("086") and _CN_MOBILE.match(text[3:]):
        # 「086-13800138000」严格说不规范（国际前缀是 00 不是 0），但国内用户
        # 写得很多，且 0 + 86 + 合法手机号没有别的解释，按 +86 处理。
        return "+" + text[1:]

    if not text.isdigit():
        raise InvalidPhoneError("手机号格式不正确")
    if _CN_MOBILE.match(text):
        # 裸 11 位手机号按默认国家码补全（老版本 App 只填 11 位，保持兼容）。
        return f"+{settings.DEFAULT_PHONE_COUNTRY_CODE}{text}"
    if text.startswith(settings.DEFAULT_PHONE_COUNTRY_CODE) and _CN_MOBILE.match(
        text[len(settings.DEFAULT_PHONE_COUNTRY_CODE):]
    ):
        # 用户写了 8613800138000 这种不带 + 的形式
        return f"+{text}"

    # 其它裸数字无法确定国家码，明确拒绝，不要瞎猜（猜错会把号发去别的国家）。
    raise InvalidPhoneError("手机号格式不正确")


def normalize_phone(raw: str) -> str:
    """把各种写法的手机号归一化成 E.164。

    Raises:
        InvalidPhoneError: 格式不合法或号段不存在。
    """
    candidate = _to_e164_candidate(raw)

    try:
        parsed = phonenumbers.parse(candidate, None)
    except phonenumbers.NumberParseException as exc:
        raise InvalidPhoneError("手机号格式不正确") from exc

    # is_valid_number 做的是「这个号段在该国真实存在」的校验，比单纯的位数校验强得多：
    # +8612345、+1 后面跟一个不存在的区号，都能被这一步挡下。
    if not phonenumbers.is_valid_number(parsed):
        raise InvalidPhoneError("手机号格式不正确")

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def split_e164(e164: str) -> tuple[str, str]:
    """E.164 → (国家码, 国内号码)，都是纯数字串。

    阿里云号码认证服务的 SendSmsVerifyCode / CheckSmsVerifyCode 要求把国家码
    （CountryCode）和号码（PhoneNumber，不含国家码的国内号）分开传：国内号
    CountryCode=86、PhoneNumber 是 11 位裸号；国际号同理，各自的国家码 + 国内号。
    统一按 phonenumbers 拆，避免对 +86 特判、对其它国家又走另一套逻辑。
    """
    parsed = phonenumbers.parse(e164, None)
    country_code = str(parsed.country_code)
    # 直接从 E.164 去掉「+国家码」拿国内号，而不是走 NATIONAL 格式化：后者会带上
    # 国内长途前缀（如英国的前导 0）和分隔符，阿里云都不认。这样得到的纯数字串
    # 也总能和国家码拼回原始 E.164。
    national = e164.lstrip("+")[len(country_code):]
    return country_code, national


def is_domestic(e164: str) -> bool:
    """是否为默认国家（中国大陆）号码。用于在国内/国际短信模板间分流。"""
    return e164.startswith(f"+{settings.DEFAULT_PHONE_COUNTRY_CODE}")


def to_aliyun_format(e164: str) -> str:
    """E.164 → 阿里云 SendSms 要求的 PhoneNumbers 格式。

    ⚠️ 缠论 App 已改用 split_e164（国家码与号码分开传，见 services/account/codes.py），
    这个函数仅为 WordLens（背单词）保留：它对国内号要 11 位裸号（带 +86 会被拒），
    对国际号要 00 开头而不是 +。
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
