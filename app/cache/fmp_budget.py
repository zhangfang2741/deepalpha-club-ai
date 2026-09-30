"""FMP 全局调用预算：按分钟计数（Redis 固定窗口，跨进程共享）+ 批量任务熔断。

套餐实测 300 次/分钟。所有 FMP 调用前先 acquire：
- 总量每分钟不超过 FMP_RATE_LIMIT_PER_MIN；
- 批量任务（priority="batch"）另有 FMP_BATCH_RATE_LIMIT_PER_MIN 上限，给线上用户请求留余量；
- 批量任务遇到任一 429 → report_429 设熔断键，所有批量调用暂停 FMP_BATCH_BREAKER_SECONDS，
  用户请求照常。
Redis 不可用或出错时退化为进程内计数（不跨进程，但不会让 FMP 调用因此失败）。
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

# 进程内串行化所有 Redis 访问：批量全量是 12 信号量 × 每股 gather 3 的并发 acquire，
# 曾瞬时需要 ~36 条池连接打满 max_connections（Too many connections），降级进程内计数后
# 跨进程限流失效。预算命令是亚毫秒级的，串行化后占用恒定 ≤1 条连接，也消除分钟边界
# 集体醒来的连接风暴。锁内只做 Redis 命令，绝不 sleep。
_redis_lock = asyncio.Lock()


def _minute_keys(minute: int) -> tuple[str, str]:
    return f"fmp:budget:{minute}", f"fmp:budget:batch:{minute}"


def _local_incr(key: str) -> int:
    if len(_local_counts) > 100:  # Redis 长时间不可用时别让分钟计数无限增长
        suffix = key.rsplit(":", 1)[-1]
        for k in [k for k in _local_counts if not k.endswith(suffix)]:
            del _local_counts[k]
    _local_counts[key] = _local_counts.get(key, 0) + 1
    return _local_counts[key]


async def _incr(redis: Redis | None, key: str) -> int:
    """分钟计数；Redis 出错时退回进程内计数（限流降级为单进程，但不让 FMP 调用因此失败）。"""
    if redis is None:
        return _local_incr(key)
    try:
        n = int(await redis.incr(key))
        if n == 1:
            await redis.expire(key, _WINDOW_TTL)
        return n
    except Exception as e:  # noqa: BLE001
        logger.warning("fmp_budget_redis_error", op="incr", error=str(e))
        return _local_incr(key)


async def _breaker_remaining(redis: Redis | None, now: float) -> float:
    local = max(0.0, _local_breaker_until - now)
    if redis is None:
        return local
    try:
        ttl = int(await redis.ttl(BREAKER_KEY))
    except Exception as e:  # noqa: BLE001
        logger.warning("fmp_budget_redis_error", op="ttl", error=str(e))
        return local
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
        minute = int(t // 60)
        key_total, key_batch = _minute_keys(minute)
        until_next_minute = (minute + 1) * 60 - t + 0.05
        # 一轮判断的 Redis 命令持锁串行（见 _redis_lock 注释）；sleep 在锁外，
        # 多个等待者醒来后在锁上排队，天然错峰
        async with _redis_lock:
            wait = await _breaker_remaining(redis, t) if priority == "batch" else 0.0
            over_batch = over_total = False
            if wait <= 0:
                over_batch = (priority == "batch"
                              and await _incr(redis, key_batch) > limit_batch)
                over_total = not over_batch and await _incr(redis, key_total) > limit_total
        if wait > 0:
            await sleep(wait)
            continue
        if over_batch or over_total:
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
    _local_breaker_until = now() + seconds  # 本进程总是记一份，Redis 出错时也能熔断
    if redis is None:
        return
    try:
        async with _redis_lock:
            await redis.set(BREAKER_KEY, "1", ex=seconds)
    except Exception as e:  # noqa: BLE001
        logger.warning("fmp_budget_redis_error", op="set_breaker", error=str(e))


def reset_local_state() -> None:
    """测试用：清空进程内计数与熔断。"""
    global _local_breaker_until
    _local_counts.clear()
    _local_breaker_until = 0.0
