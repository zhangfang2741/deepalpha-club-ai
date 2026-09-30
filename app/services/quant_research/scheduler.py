"""量化研究夜间调度（进程内）。

美股批量：美股交易日收盘后的次日早上（默认 UTC 22:30 = 北京 06:30，排在雷达美股预热之后），
周二 ~ 周六触发（对应周一 ~ 周五的收盘）。A 股预期快照：工作日 UTC 09:00（北京 17:00）。
多实例部署时用 Redis 锁保证同一天只跑一次。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

import httpx

from app.cache.client import current_redis
from app.cache.operations import acquire_lock
from app.core.config import settings
from app.core.logging import logger
from app.services.quant_research.batch import run_cn_estimate_snapshot, run_us_batch

_LOCK_TTL = 6 * 3600


def next_trigger(after: datetime, hour: int, minute: int, weekdays: set[int]) -> datetime:
    """计算 after 之后最近一个 weekday ∈ weekdays、时刻为 hour:minute（UTC）的时间点。"""
    after = after.astimezone(UTC)
    t = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if t <= after:
        t += timedelta(days=1)
    while t.weekday() not in weekdays:
        t += timedelta(days=1)
    return t


def us_session_date(trigger: datetime) -> date:
    """UTC 22:30 触发时，对应的美股交易日就是当天（美东收盘 20:00/21:00 UTC 之后）。"""
    return trigger.astimezone(UTC).date()


async def _run_once(kind: str, day: date) -> None:
    redis = current_redis()
    if redis is not None and not await acquire_lock(redis, f"quant:batch_lock:{kind}:{day.isoformat()}", _LOCK_TTL):
        logger.info("quant_batch_skipped_locked", kind=kind, day=day.isoformat())
        return
    if kind == "us":
        async with httpx.AsyncClient() as client:
            await run_us_batch(day, redis=redis, client=client)
    else:
        await run_cn_estimate_snapshot(day)


async def _loop(kind: str, hour: int, minute: int, weekdays: set[int]) -> None:
    while True:
        trigger = next_trigger(datetime.now(UTC), hour, minute, weekdays)
        try:
            await asyncio.sleep(max(0.0, (trigger - datetime.now(UTC)).total_seconds()))
        except asyncio.CancelledError:
            return
        try:
            await _run_once(kind, us_session_date(trigger) if kind == "us" else trigger.date())
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("quant_batch_loop_failed", kind=kind, error=str(e))


async def run_quant_scheduler() -> None:
    """美股批量 + A 股快照两个循环，直到进程退出。"""
    if not settings.QUANT_BATCH_ENABLED:
        logger.info("quant_batch_disabled")
        return
    await asyncio.gather(
        _loop("us", settings.QUANT_BATCH_UTC_HOUR, settings.QUANT_BATCH_UTC_MINUTE, {0, 1, 2, 3, 4}),
        _loop("cn", settings.QUANT_CN_SNAPSHOT_UTC_HOUR, 0, {0, 1, 2, 3, 4}),
    )
