"""统一登录的账号标识判别。

登录框只有一个输入框，用户输手机号还是邮箱由服务端认。判别顺序是「先试手机号，
不成再当邮箱」而不是反过来：手机号的格式约束严格得多（中国大陆 11 位、号段固定），
误判概率极低；邮箱格式则宽松，`13800138000` 之类的输入不该先被邮箱校验拦下。
"""
from __future__ import annotations

from enum import Enum

from app.utils.phone import InvalidPhoneError, normalize_phone
from app.utils.sanitization import sanitize_email


class AccountKind(str, Enum):
    """账号标识的类型。"""

    PHONE = "phone"
    EMAIL = "email"


def resolve_account(raw: str) -> tuple[AccountKind, str]:
    """判别账号是手机号还是邮箱，并归一化。

    Args:
        raw: 用户在登录框里输入的原始内容。

    Returns:
        (类型, 归一化后的值)。手机号是 E.164，邮箱是小写去空白。

    Raises:
        ValueError: 两种格式都不满足。
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("请输入手机号或邮箱")

    try:
        return AccountKind.PHONE, normalize_phone(text)
    except InvalidPhoneError:
        pass

    # 纯数字走到这里说明它不是合法手机号。继续当邮箱处理只会给出「邮箱格式不正确」
    # 这种更让人困惑的报错，不如直接按手机号报错。
    if text.replace("+", "").isdigit():
        raise ValueError("手机号格式不正确")

    try:
        return AccountKind.EMAIL, sanitize_email(text)
    except ValueError as exc:
        raise ValueError("请输入正确的手机号或邮箱") from exc
