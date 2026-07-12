"""Sign in with Apple：校验 Apple 下发的身份令牌（identity token）。.

流程：
1. 从 Apple 的 JWKS 端点拉取公钥（带内存缓存）。
2. 用令牌 header 里的 kid 找到对应公钥。
3. 校验签名、issuer、audience（= App Bundle ID）、过期时间。
4. 返回 Apple 用户唯一标识 sub 与邮箱。

不依赖 Apple Developer 账号的服务端密钥：仅做身份令牌的公钥验签即可，
适用于 iOS 原生 Sign in with Apple（audience 为 App 的 Bundle ID）。
"""
from __future__ import annotations

import time
from typing import Any

import httpx
from jose import jwt
from jose.exceptions import JWTError

from app.core.config import settings
from app.core.logging import logger

_APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
_APPLE_ISSUER = "https://appleid.apple.com"

# JWKS 内存缓存（Apple 公钥轮换不频繁，缓存 1 小时）
_keys_cache: dict[str, Any] = {"keys": None, "fetched_at": 0.0}
_CACHE_TTL = 3600.0


class AppleAuthError(Exception):
    """Apple 身份令牌校验失败。."""


async def _fetch_apple_keys(force: bool = False) -> list[dict[str, Any]]:
    """拉取并缓存 Apple 公钥集合。."""
    now = time.monotonic()
    if not force and _keys_cache["keys"] is not None and now - _keys_cache["fetched_at"] < _CACHE_TTL:
        return _keys_cache["keys"]

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(_APPLE_KEYS_URL)
        resp.raise_for_status()
        keys = resp.json().get("keys", [])

    _keys_cache["keys"] = keys
    _keys_cache["fetched_at"] = now
    return keys


async def verify_identity_token(identity_token: str) -> dict[str, Any]:
    """校验 Apple 身份令牌，返回其 claims（含 sub、email）。.

    Args:
        identity_token: iOS 端 Sign in with Apple 返回的 identityToken 字符串。

    Returns:
        dict: 校验通过后的 JWT claims。

    Raises:
        AppleAuthError: 令牌无效、签名不符或字段校验失败。
    """
    try:
        unverified_header = jwt.get_unverified_header(identity_token)
    except JWTError as e:
        raise AppleAuthError("身份令牌格式无效") from e

    kid = unverified_header.get("kid")
    if not kid:
        raise AppleAuthError("身份令牌缺少 kid")

    keys = await _fetch_apple_keys()
    matching = next((k for k in keys if k.get("kid") == kid), None)
    if matching is None:
        # 公钥可能已轮换，强制刷新一次再找
        keys = await _fetch_apple_keys(force=True)
        matching = next((k for k in keys if k.get("kid") == kid), None)
    if matching is None:
        raise AppleAuthError("找不到匹配的 Apple 公钥")

    try:
        claims = jwt.decode(
            identity_token,
            matching,
            algorithms=["RS256"],
            audience=settings.APPLE_CLIENT_ID,
            issuer=_APPLE_ISSUER,
        )
    except JWTError as e:
        logger.warning("apple_token_verification_failed", error=str(e))
        raise AppleAuthError("身份令牌校验未通过") from e

    if not claims.get("sub"):
        raise AppleAuthError("身份令牌缺少用户标识")

    return claims
