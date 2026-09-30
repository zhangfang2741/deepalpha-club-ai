"""FMP 全局调用预算：按分钟计数（Redis 固定窗口，跨进程共享）+ 批量任务熔断。

套餐实测 300 次/分钟。所有 FMP 调用前先 acquire：
- 总量每分钟不超过 FMP_RATE_LIMIT_PER_MIN；
- 批量任务（priority="batch"）另有 FMP_BATCH_RATE_LIMIT_PER_MIN 上限，给线上用户请求留余量；
- 批量任务遇到任一 429 → report_429 设熔断键，所有批量调用暂停 FMP_BATCH_BREAKER_SECONDS，
  用户请求照常。
Redis 不可用时退化为进程内计数（本地 / 测试可跑，但不跨进程）。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Literal

from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import logger

Priority = Literal["user", "batch"]
BREAKER_KEY = "fmp:breaker:batch"
_WINDOW_TTL = 120

_local_counts: dict[str, int] = {}
_local_breaker_until = 0.0


def _minute_keys(minute: int) -> tuple[str, str]:
    return f"fmp:budget:{minute}", f"fmp:budget:batch:{minute}"


async def _incr(redis: Redis | None, key: str) -> int:
    if redis is None:
        _local_counts[key] = _local_counts.get(key, 0) + 1
        return _local_counts[key]
    n = int(await redis.incr(key))
    if n == 1:
        await redis.expire(key, _WINDOW_TTL)
    return n


async def _breaker_remaining(redis: Redis | None, now: float) -> float:
    if redis is None:
        return max(0.0, _local_breaker_until - now)
    ttl = int(await redis.ttl(BREAKER_KEY))
    return float(ttl) if ttl > 0 else 0.0


async def acquire(
    redis: Redis | None,
    priority: Priority,
    *,
    now: Callable[[], float] = time.time,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    limit_total: int | None = None,
    limit_batch: int | None = None,
) -> None:
    """拿到一次调用额度才返回；额度用完就睡到下一分钟再试。"""
    limit_total = limit_total or settings.FMP_RATE_LIMIT_PER_MIN
    limit_batch = limit_batch or settings.FMP_BATCH_RATE_LIMIT_PER_MIN
    while True:
        t = now()
        if priority == "batch":
            wait = await _breaker_remaining(redis, t)
            if wait > 0:
                await sleep(wait)
                continue
        minute = int(t // 60)
        key_total, key_batch = _minute_keys(minute)
        until_next_minute = (minute + 1) * 60 - t + 0.05
        if priority == "batch" and await _incr(redis, key_batch) > limit_batch:
            await sleep(until_next_minute)
            continue
        if await _incr(redis, key_total) > limit_total:
            await sleep(until_next_minute)
            continue
        return


async def report_429(redis: Redis | None, priority: Priority, *, now: Callable[[], float] = time.time) -> None:
    """记录一次 429；批量任务整体熔断。"""
    global _local_breaker_until
    logger.warning("fmp_rate_limited", priority=priority)
    if priority != "batch":
        return
    seconds = settings.FMP_BATCH_BREAKER_SECONDS
    if redis is None:
        _local_breaker_until = now() + seconds
        return
    await redis.set(BREAKER_KEY, "1", ex=seconds)


def reset_local_state() -> None:
    """测试用：清空进程内计数与熔断。"""
    global _local_breaker_until
    _local_counts.clear()
    _local_breaker_until = 0.0
