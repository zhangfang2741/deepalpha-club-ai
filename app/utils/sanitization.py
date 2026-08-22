"""This file contains the sanitization utilities for the application."""

import html
import re
from typing import (
    Any,
    Dict,
    List,
)


def sanitize_string(value: str) -> str:
    """Sanitize a string to prevent XSS and other injection attacks.

    Args:
        value: The string to sanitize

    Returns:
        str: The sanitized string
    """
    # Convert to string if not already
    if not isinstance(value, str):
        value = str(value)

    # HTML escape to prevent XSS
    value = html.escape(value)

    # Remove any script tags that might have been escaped
    value = re.sub(r"&lt;script.*?&gt;.*?&lt;/script&gt;", "", value, flags=re.DOTALL)

    # Remove null bytes
    value = value.replace("\0", "")

    return value


def sanitize_email(email: str) -> str:
    """Sanitize an email address.

    Args:
        email: The email address to sanitize

    Returns:
        str: The sanitized email address
    """
    # Basic sanitization
    email = sanitize_string(email)

    # Ensure email format (simple check)
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        raise ValueError("Invalid email format")

    return email.lower()


def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively sanitize all string values in a dictionary.

    Args:
        data: The dictionary to sanitize

    Returns:
        Dict[str, Any]: The sanitized dictionary
    """
    sanitized = {}
    for key, value in data.items():
        if isinstance(value, str):
            sanitized[key] = sanitize_string(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value)
        elif isinstance(value, list):
            sanitized[key] = sanitize_list(value)
        else:
            sanitized[key] = value
    return sanitized


def sanitize_list(data: List[Any]) -> List[Any]:
    """Recursively sanitize all string values in a list.

    Args:
        data: The list to sanitize

    Returns:
        List[Any]: The sanitized list
    """
    sanitized = []
    for item in data:
        if isinstance(item, str):
            sanitized.append(sanitize_string(item))
        elif isinstance(item, dict):
            sanitized.append(sanitize_dict(item))
        elif isinstance(item, list):
            sanitized.append(sanitize_list(item))
        else:
            sanitized.append(item)
    return sanitized


def validate_password_strength(password: str) -> bool:
    """Validate password strength: at least 8 characters, with letters and digits.

    这是主站密码规则的**唯一**实现，schemas/auth.py 里的两个 validator 都委托
    到这里。曾经三处各写一份，改一处会漏另外两处。

    不再要求大小写区分和特殊字符：那套规则（8 位 + 大写 + 小写 + 数字 + 特殊
    字符）对普通用户太苛刻，实际效果是逼人用 `Password1!` 这类既难记又没多少
    熵的密码，安全收益并不比「字母 + 数字 + 足够长」高。

    Args:
        password: The password to validate

    Returns:
        bool: Whether the password is strong enough

    Raises:
        ValueError: If the password is not strong enough with reason
    """
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")

    if not re.search(r"[A-Za-z]", password):
        raise ValueError("Password must contain at least one letter")

    if not re.search(r"[0-9]", password):
        raise ValueError("Password must contain at least one number")

    return True


#: WordLens 密码最短长度。改这里要同步 app/schemas/vocabulary.py 的 min_length
#: 和 iOS 端 RegisterView / AccountSecurityView 的提示文案。
VOCABULARY_PASSWORD_MIN_LENGTH = 6


def validate_vocabulary_password_strength(password: str) -> bool:
    """校验 WordLens（背单词 App）密码强度：只看长度，不做字符组合要求。

    WordLens 账号体系跟主站完全独立（见 app/models/vocabulary.py），面向个人背单词
    场景，主站 validate_password_strength() 的复杂度要求对这个场景太重。

    这里刻意不要求「必须含字母/数字/特殊字符」：NIST SP 800-63B 明确建议废弃组合
    规则，理由是它并不提升实际强度，反而把用户推向 `Password1` `abc12345` 这类高度
    可预测的模式，同时显著抬高注册流失。长度才是真正有效的强度来源。

    Args:
        password: 待校验的明文密码

    Returns:
        bool: 密码是否满足强度要求

    Raises:
        ValueError: 密码强度不够时，附带具体原因
    """
    if len(password) < VOCABULARY_PASSWORD_MIN_LENGTH:
        raise ValueError(f"密码至少需要 {VOCABULARY_PASSWORD_MIN_LENGTH} 个字符")

    return True
