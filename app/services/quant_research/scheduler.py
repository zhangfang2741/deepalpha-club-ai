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
from app.cache.operations import acquire_lock, release_lock
from app.core.config import settings
from app.core.logging import logger
from app.services.quant_research import repository as repo
from app.services.quant_research.batch import run_cn_estimate_snapshot, run_us_batch
from app.services.quant_research.builder import METHODOLOGY_VERSION
from app.services.quant_research.moat import METHOD_VERSION as MOAT_METHOD_VERSION
from app.services.quant_research.moat.job import run_moat_job

# 批量锁 TTL：最长的一轮（约 1500 只股票、每只约 4 次调用，批量限速 150/分钟）约 40 分钟，90 分钟足够。
# 不能再长：部署会杀掉跑批中的进程，锁留在 Redis 里挡住下一次自举（2026-09-30 踩过 6h 死锁）。
_LOCK_TTL = 15 * 60  # 短锁 + 心跳：部署重启后旧锁 15 分钟内过期（曾因 90 分钟死锁让 q6 冷启动多等 1 小时）
_LOCK_RENEW_SECONDS = 5 * 60
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


async def _results_current() -> bool:
    """已有批量结果，且方法版本与当前代码一致。"""
    if await repo.latest_distribution_date("us") is None:
        return False
    return await repo.latest_methodology_version("us") == METHODOLOGY_VERSION


async def _bootstrap_once() -> None:
    """冷启动自举：没跑过批量、或已存结果的方法版本与代码不一致时，启动后立即跑一次全量。

    首次部署若等到定时点（北京时间 06:30），白天所有请求都会拿到「数据尚未生成」或旧口径结果；
    自举让新结果在部署后 ~1 小时内可用。锁键带方法版本：多实例只跑一次，
    也不会被当天已跑完的夜间批量锁挡住。
    """
    try:
        await _align_backfill()
        await asyncio.sleep(BOOTSTRAP_DELAY_SECONDS)
        for attempt in range(BOOTSTRAP_MAX_ATTEMPTS):
            if await _results_current():
                return
            logger.info("quant_batch_bootstrap_attempt", attempt=attempt, version=METHODOLOGY_VERSION)
            # 锁被占（别的实例在跑 / 上一进程留下的锁）时 _run_once 只记日志不抛错，
            # 这里靠重试等它跑完或过期，而不是放弃到下一个定时点
            await _run_once("us", last_us_session(datetime.now(UTC)), lock_suffix=METHODOLOGY_VERSION)
            if await _results_current():
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


async def _run_once(kind: str, day: date, *, lock_suffix: str | None = None) -> None:
    redis = current_redis()
    key = _lock_key(kind, day) + (f":{lock_suffix}" if lock_suffix else "")
    if redis is not None and not await acquire_lock(redis, key, _LOCK_TTL):
        logger.info("quant_batch_skipped_locked", kind=kind, day=day.isoformat())
        return
    # 跑的过程中续期；跑完不删锁，让它自然过期，短时间内其它实例 / 触发不会重复跑
    renew = asyncio.create_task(_renew(redis, key, _LOCK_TTL, _LOCK_RENEW_SECONDS)) if redis is not None else None
    try:
        if kind == "us":
            async with httpx.AsyncClient() as client:
                await run_us_batch(day, redis=redis, client=client)
        else:
            await run_cn_estimate_snapshot(day)
    finally:
        if renew is not None:
            renew.cancel()


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


MOAT_LOCK_TTL = 15 * 60          # 短锁 + 心跳：进程被重启后锁很快过期，新进程能接着跑
MOAT_LOCK_RENEW_SECONDS = 5 * 60
MOAT_BOOTSTRAP_RETRY_SECONDS = 10 * 60
MOAT_BOOTSTRAP_MAX_ATTEMPTS = 12


def _moat_lock_key() -> str:
    return f"quant:moat_lock:{MOAT_METHOD_VERSION}"


async def _renew(redis: object, key: str, ttl: int, every: int) -> None:
    """锁心跳：任务运行期间定期续期，进程被杀后锁在 ttl 内自然过期。"""
    while True:
        await asyncio.sleep(every)
        await redis.expire(key, ttl)  # type: ignore[attr-defined]


async def _run_moat_once() -> bool:
    """跑一轮护城河任务；锁被占（别的实例 / 刚重启前的进程还在跑）返回 False。已评估的年报会跳过。"""
    redis = current_redis()
    key = _moat_lock_key()
    if redis is not None and not await acquire_lock(redis, key, MOAT_LOCK_TTL):
        logger.info("quant_moat_skipped_locked")
        return False
    renew = asyncio.create_task(_renew(redis, key, MOAT_LOCK_TTL, MOAT_LOCK_RENEW_SECONDS)) if redis is not None else None
    try:
        await run_moat_job(redis)
    finally:
        if renew is not None:
            renew.cancel()
        if redis is not None:
            await release_lock(redis, key)
    return True


async def _moat_loop() -> None:
    """部署后先冷启动跑一遍（补齐没评估过的；锁被占就过会儿再试），之后每天检查一次新 10-K。"""
    try:
        await asyncio.sleep(BOOTSTRAP_DELAY_SECONDS)
        for _ in range(MOAT_BOOTSTRAP_MAX_ATTEMPTS):
            if await _run_moat_once():
                break
            await asyncio.sleep(MOAT_BOOTSTRAP_RETRY_SECONDS)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 冷启动失败不影响每日循环
        logger.exception("quant_moat_bootstrap_failed", error=str(e))
    while True:
        trigger = next_trigger(datetime.now(UTC), settings.QUANT_MOAT_UTC_HOUR, 0, {0, 1, 2, 3, 4, 5, 6})
        try:
            await asyncio.sleep(max(0.0, (trigger - datetime.now(UTC)).total_seconds()))
        except asyncio.CancelledError:
            return
        try:
            await _run_moat_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("quant_moat_loop_failed", error=str(e))


async def run_quant_scheduler() -> None:
    """美股批量 + A 股快照两个循环，直到进程退出。"""
    if not settings.QUANT_BATCH_ENABLED:
        logger.info("quant_batch_disabled")
        return
    tasks = [_moat_loop()] if settings.QUANT_MOAT_ENABLED else []
    await asyncio.gather(
        *tasks,
        _bootstrap_once(),
        _loop("us", settings.QUANT_BATCH_UTC_HOUR, settings.QUANT_BATCH_UTC_MINUTE, {0, 1, 2, 3, 4}),
        _loop("cn", settings.QUANT_CN_SNAPSHOT_UTC_HOUR, 0, {0, 1, 2, 3, 4}),
    )
