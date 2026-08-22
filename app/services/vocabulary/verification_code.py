"""WordLens 的验证码存储。

实现已提升到 app.services.verification_code 供多个 App 共用，这里只保留一个
绑定了 vocab:vercode 前缀的实例，以及与提升前完全一致的模块级函数签名——
调用方（vocabulary/auth.py）和既有测试都不需要改动，线上 Redis 里在途的
验证码 key 也不会变。
"""
from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import settings as settings  # noqa: F401  测试引用 ec.settings
from app.services.verification_code import (
    CodeStore,
    Purpose as Purpose,
    ResendTooSoonError as ResendTooSoonError,
    TooManyAttemptsError as TooManyAttemptsError,
    _hash_code as _hash_code,
    _slug as _slug,
    generate_code as generate_code,
)

_store = CodeStore("vocab:vercode")


async def issue_code(redis: Redis, purpose: Purpose, identifier: str) -> str:
    """签发验证码。见 CodeStore.issue_code。"""
    return await _store.issue_code(redis, purpose, identifier)


async def verify_code(redis: Redis, purpose: Purpose, identifier: str, code: str) -> bool:
    """校验验证码。见 CodeStore.verify_code。"""
    return await _store.verify_code(redis, purpose, identifier, code)


async def discard_code(redis: Redis, purpose: Purpose, identifier: str) -> None:
    """作废验证码并解除冷却。见 CodeStore.discard_code。"""
    await _store.discard_code(redis, purpose, identifier)


async def is_cooling_down(redis: Redis, purpose: Purpose, identifier: str) -> bool:
    """是否还在冷却期。见 CodeStore.is_cooling_down。"""
    return await _store.is_cooling_down(redis, purpose, identifier)


async def start_cooldown(redis: Redis, purpose: Purpose, identifier: str) -> None:
    """上冷却并重置错误计数。见 CodeStore.start_cooldown。"""
    await _store.start_cooldown(redis, purpose, identifier)


async def assert_attempts_left(redis: Redis, purpose: Purpose, identifier: str) -> None:
    """错误次数用尽则抛异常。见 CodeStore.assert_attempts_left。"""
    await _store.assert_attempts_left(redis, purpose, identifier)


async def record_failed_attempt(redis: Redis, purpose: Purpose, identifier: str) -> None:
    """记一次校验失败。见 CodeStore.record_failed_attempt。"""
    await _store.record_failed_attempt(redis, purpose, identifier)


async def clear_attempts(redis: Redis, purpose: Purpose, identifier: str) -> None:
    """清掉错误计数。见 CodeStore.clear_attempts。"""
    await _store.clear_attempts(redis, purpose, identifier)
