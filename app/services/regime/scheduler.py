"""市场状态（大盘 + 行业）每日重算（进程内调度）。

美股收盘后（UTC 22:45，周二 ~ 周六，对应周一 ~ 周五的收盘）跑一次大盘与行业两条管线并落库；
启动时若库里最新交易日落后于最近一个已收盘交易日，先补跑一次。多实例用 Redis 锁保证同一天只跑一次。
每轮约 45 次 FMP 调用（沿用 regime fetcher 的同步取数）。跑完清掉宏观弹层 / 摘要缓存。

计算很重（大盘 + 39 个行业各做一次走前向 HMM，逐月重估，单线程约 35~40 分钟），放在独立子进程里
跑并调低优先级：纯 Python 循环会长时间占住 GIL，放线程池会拖慢同进程的 API 请求。
"""
from __future__ import annotations

import asyncio
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, date, datetime

from sqlmodel import col, select

from app.cache import macro_cache
from app.cache.client import current_redis
from app.cache.operations import acquire_lock
from app.core.logging import logger
from app.services.quant_research.scheduler import last_us_session, next_trigger

_TRIGGER_HOUR, _TRIGGER_MINUTE = 22, 45
_WEEKDAYS = {1, 2, 3, 4, 5}
_STARTUP_DELAY_SECONDS = 90
_LOCK_TTL = 2 * 3600  # 长于一整轮（约 40 分钟），部署中断后最迟两小时可重跑


def _latest_dates() -> tuple[str | None, str | None]:
    from app.db.session import get_sync_session_cm
    from app.models.regime_features import RegimeFeatures
    from app.models.regime_sector_features import RegimeSectorFeatures

    with get_sync_session_cm() as session:
        market = session.exec(
            select(RegimeFeatures.trade_date).order_by(col(RegimeFeatures.trade_date).desc()).limit(1)).first()
        sector = session.exec(
            select(RegimeSectorFeatures.trade_date)
            .order_by(col(RegimeSectorFeatures.trade_date).desc()).limit(1)).first()
    return market, sector


def is_stale(latest_market: str | None, latest_sector: str | None, session_day: date) -> bool:
    """任一张表没有数据，或最新交易日早于最近一个已收盘交易日（节假日会多补跑一次，无害）。"""
    target = session_day.isoformat()
    return latest_market is None or latest_sector is None or latest_market < target or latest_sector < target


def _run_stages() -> dict:
    from app.db.session import get_sync_session_cm
    from app.services.regime.pipeline import run_regime_stage
    from app.services.regime.sector_pipeline import run_sector_regime_stage

    with get_sync_session_cm() as session:
        market = run_regime_stage(session)
    with get_sync_session_cm() as session:
        sector = run_sector_regime_stage(session)
    return {"market_latest": market.get("latest_date"), "sectors": sector.get("sectors")}


def _run_stages_low_priority() -> dict:
    """子进程入口：先降低调度优先级，再跑两条管线。"""
    try:
        os.nice(10)
    except OSError:
        pass
    return _run_stages()


async def run_once(session_day: date) -> None:
    """跑一轮大盘 + 行业 regime（同一交易日多实例只跑一次）。"""
    redis = current_redis()
    if redis is not None and not await acquire_lock(redis, f"regime:run:{session_day.isoformat()}", _LOCK_TTL):
        logger.info("regime_daily_skipped_locked", session=session_day.isoformat())
        return
    try:
        loop = asyncio.get_running_loop()
        with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as pool:
            summary = await loop.run_in_executor(pool, _run_stages_low_priority)
        logger.info("regime_daily_done", session=session_day.isoformat(), **summary)
        await macro_cache.drop_market(redis, "us")
    except Exception as e:  # noqa: BLE001
        logger.exception("regime_daily_failed", session=session_day.isoformat(), error=str(e))


async def run_regime_scheduler() -> None:
    """进程内调度循环：启动补跑 + 每个美股交易日收盘后重算。"""
    await asyncio.sleep(_STARTUP_DELAY_SECONDS)
    try:
        session_day = last_us_session(datetime.now(UTC))
        if is_stale(*await asyncio.to_thread(_latest_dates), session_day):
            await run_once(session_day)
    except Exception as e:  # noqa: BLE001
        logger.exception("regime_bootstrap_failed", error=str(e))
    while True:
        now = datetime.now(UTC)
        trigger = next_trigger(now, _TRIGGER_HOUR, _TRIGGER_MINUTE, _WEEKDAYS)
        await asyncio.sleep(max(0.0, (trigger - now).total_seconds()))
        await run_once(trigger.date())
