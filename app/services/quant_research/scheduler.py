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
from app.services.quant_research import repository as repo
from app.services.quant_research.batch import run_cn_estimate_snapshot, run_us_batch

# 批量锁 TTL：最长的一轮（约 1500 只股票、每只约 4 次调用，批量限速 150/分钟）约 40 分钟，90 分钟足够。
# 不能再长：部署会杀掉跑批中的进程，锁留在 Redis 里挡住下一次自举（2026-09-30 踩过 6h 死锁）。
_LOCK_TTL = 90 * 60
BOOTSTRAP_RETRY_SECONDS = 10 * 60
BOOTSTRAP_MAX_ATTEMPTS = 12  # 重试共 ~2 小时；之后再等当天的定时点


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


def last_us_session(now: datetime) -> date:
    """最近一个已收盘的美股交易日：now 晚于当日 UTC 22:30（收盘 + 数据源缓冲）取当天，否则取前一个工作日。

    定时批量在 22:30 触发时结果与 us_session_date 一致；冷启动自举在任意时刻调用也得到正确口径。
    """
    now = now.astimezone(UTC)
    sess = now.date()
    if now < now.replace(hour=22, minute=30, second=0, microsecond=0):
        sess -= timedelta(days=1)
    while sess.weekday() >= 5:
        sess -= timedelta(days=1)
    return sess


BOOTSTRAP_DELAY_SECONDS = 120


async def _drop_radar_snapshots(redis: object) -> None:
    """评级可用性变化后清掉雷达快照缓存，让下一轮扫描带着评级重排。

    键前缀与 signal_radar service._CACHE_PREFIX 一致（含每日快照 / 自选 / 示例日 /
    generating 锁，后三者清掉最多触发一次重算，无害）。
    """
    keys = [k async for k in redis.scan_iter(match="signal_radar:*", count=200)]  # type: ignore[attr-defined]
    if keys:
        await redis.unlink(*keys)  # type: ignore[attr-defined]


async def _align_backfill() -> None:
    """启动时把补跑写入的评级行时间戳对齐回定时跑批时刻（幂等，见 repository 同名函数）。

    2026-09-30 上线首日：自举在白天补跑 as_of=9-29 的批量，created_at=9-30 让全部
    评级对当时的雷达展示日不可用（iOS 气泡无评级角标）。对齐后昨天的展示日即可用。
    """
    rows = await repo.align_backfill_timestamps("us", settings.QUANT_BATCH_UTC_HOUR,
                                                settings.QUANT_BATCH_UTC_MINUTE)
    if rows:
        logger.info("quant_backfill_timestamps_aligned", market="us", rows=rows)
        redis = current_redis()
        if redis is not None:
            await _drop_radar_snapshots(redis)


async def _bootstrap_once() -> None:
    """冷启动自举：从未跑过批量（没有任何板块分布）时，启动后先跑一次首次全量。

    首次部署若等到定时点（北京时间 06:30），白天所有请求都会拿到「数据尚未生成」；
    自举让结果在部署后 ~1 小时内可用。多实例 / 与定时批量并发由 Redis 锁保证只跑一次。
    """
    try:
        await _align_backfill()
        await asyncio.sleep(BOOTSTRAP_DELAY_SECONDS)
        for attempt in range(BOOTSTRAP_MAX_ATTEMPTS):
            if await repo.latest_distribution_date("us") is not None:
                return
            logger.info("quant_batch_bootstrap_attempt", attempt=attempt)
            # 锁被占（别的实例在跑 / 上一进程留下的锁）时 _run_once 只记日志不抛错，
            # 这里靠重试等它跑完或过期，而不是放弃到下一个定时点
            await _run_once("us", last_us_session(datetime.now(UTC)))
            if await repo.latest_distribution_date("us") is not None:
                return
            await asyncio.sleep(BOOTSTRAP_RETRY_SECONDS)
        logger.warning("quant_batch_bootstrap_gave_up", attempts=BOOTSTRAP_MAX_ATTEMPTS)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 自举失败不影响调度循环，定时批量会再跑
        logger.exception("quant_batch_bootstrap_failed", error=str(e))


def _lock_key(kind: str, day: date) -> str:
    """批量锁键。v2：跳过 2026-09-30 部署重启留下的 v1 6 小时死锁（自然过期即可，无需清理）。"""
    return f"quant:batch_lock:v2:{kind}:{day.isoformat()}"


async def _run_once(kind: str, day: date) -> None:
    redis = current_redis()
    if redis is not None and not await acquire_lock(redis, _lock_key(kind, day), _LOCK_TTL):
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
        _bootstrap_once(),
        _loop("us", settings.QUANT_BATCH_UTC_HOUR, settings.QUANT_BATCH_UTC_MINUTE, {0, 1, 2, 3, 4}),
        _loop("cn", settings.QUANT_CN_SNAPSHOT_UTC_HOUR, 0, {0, 1, 2, 3, 4}),
    )
