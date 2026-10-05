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
    """大盘 → 一级行业 → 子行业，各自算完即落库。

    一级行业（行业格 / 行业弹层用）先落库，子行业（只用于下钻）随后：单个行业约 1 分钟，
    全部 39 个一起算完才落库的话，首次部署要等 40 分钟行业格才有数据。
    """
    from app.db.session import get_sync_session_cm
    from app.services.regime.constants import SECTOR_PARENT
    from app.services.regime.fetcher import SectorMarketData, fetch_sector_market_data
    from app.services.regime.pipeline import run_regime_stage
    from app.services.regime.sector_pipeline import compute_sector_regimes, persist_sector_records

    with get_sync_session_cm() as session:
        market = run_regime_stage(session)
    data = fetch_sector_market_data()
    primary = {k: v for k, v in data.sectors.items() if k not in SECTOR_PARENT}
    children = {k: v for k, v in data.sectors.items() if k in SECTOR_PARENT}
    written = 0
    for subset in (primary, children):
        part = SectorMarketData(dates=data.dates, vix_close=data.vix_close,
                                market_close=data.market_close, sectors=subset)
        records = compute_sector_regimes(part)
        with get_sync_session_cm() as session:
            written += persist_sector_records(session, records)
        logger.info("regime_sector_subset_done", sectors=len(subset), written=written)
    return {"market_latest": market.get("latest_date"), "sectors": len(data.sectors), "written": written}


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


# ---- A 股 / 港股大盘状态与行业状态（与美股同一套管线，见 regime/cnhk.py、cnhk_sector.py；每轮一个子进程、算完即落库） ----

_CNHK_LOCK_TTL = 20 * 60  # 一个市场约 1 分钟，短锁：部署中断后最迟 20 分钟可重跑


def _latest_cnhk_date(market: str) -> str | None:
    from app.db.session import get_sync_session_cm
    from app.models.regime_market_features import RegimeMarketFeatures

    with get_sync_session_cm() as session:
        return session.exec(
            select(RegimeMarketFeatures.trade_date).where(RegimeMarketFeatures.market == market)
            .order_by(col(RegimeMarketFeatures.trade_date).desc()).limit(1)).first()


def _latest_cnhk_sector_date(market: str) -> str | None:
    from app.db.session import get_sync_session_cm
    from app.models.regime_market_sector_features import RegimeMarketSectorFeatures as M

    with get_sync_session_cm() as session:
        return session.exec(
            select(M.trade_date).where(M.market == market).order_by(col(M.trade_date).desc()).limit(1)).first()


def is_cnhk_stale(latest: str | None, session_day: date) -> bool:
    """没有数据，或最新交易日早于最近一个已收盘的工作日（节假日会多补跑一次，无害）。"""
    return latest is None or latest < session_day.isoformat()


def _run_cnhk_stage(market: str) -> dict:
    """子进程入口：降低优先级后抓数 → 算状态 → 落库。"""
    try:
        os.nice(10)
    except OSError:
        pass
    from app.db.session import get_sync_session_cm
    from app.services.regime.cnhk import run_market_stage

    with get_sync_session_cm() as session:
        return run_market_stage(session, market)


async def run_cnhk_once(market: str, session_day: date) -> None:
    """跑一轮某个市场的大盘状态（同一交易日多实例只跑一次）。"""
    redis = current_redis()
    lock_key = f"regime:run:{market}:{session_day.isoformat()}"
    if redis is not None and not await acquire_lock(redis, lock_key, _CNHK_LOCK_TTL):
        logger.info("regime_cnhk_skipped_locked", market=market, session=session_day.isoformat())
        return
    try:
        loop = asyncio.get_running_loop()
        with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as pool:
            summary = await loop.run_in_executor(pool, _run_cnhk_stage, market)
        logger.info("regime_cnhk_daily_done", session=session_day.isoformat(), **summary)
        await macro_cache.drop_market(redis, market)
    except Exception as e:  # noqa: BLE001
        logger.exception("regime_cnhk_daily_failed", market=market, session=session_day.isoformat(), error=str(e))


_CNHK_SECTOR_LOCK_TTL = 60 * 60  # 行业状态 A 股约 8 分钟、港股约 3 分钟，长锁防止同一天被两个实例重复跑


def _run_cnhk_sector_stage(market: str) -> dict:
    """子进程入口：降低优先级后取成分股行情 → 合成行业指数 → 逐行业算状态 → 落库。"""
    try:
        os.nice(10)
    except OSError:
        pass
    from app.db.session import get_sync_session_cm
    from app.services.regime.cnhk_sector import run_sector_stage

    with get_sync_session_cm() as session:
        return run_sector_stage(session, market)


async def run_cnhk_sector_once(market: str, session_day: date) -> None:
    """跑一轮某个市场的行业状态（独立于大盘状态：单独的锁与子进程，大盘状态不用等它）。"""
    redis = current_redis()
    lock_key = f"regime:run:{market}:sector:{session_day.isoformat()}"
    if redis is not None and not await acquire_lock(redis, lock_key, _CNHK_SECTOR_LOCK_TTL):
        logger.info("regime_cnhk_sector_skipped_locked", market=market, session=session_day.isoformat())
        return
    try:
        loop = asyncio.get_running_loop()
        with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as pool:
            summary = await loop.run_in_executor(pool, _run_cnhk_sector_stage, market)
        logger.info("regime_cnhk_sector_daily_done", session=session_day.isoformat(), **summary)
        await macro_cache.drop_market(redis, market)
    except Exception as e:  # noqa: BLE001
        logger.exception("regime_cnhk_sector_daily_failed", market=market, session=session_day.isoformat(), error=str(e))


async def _cnhk_market_loop(market: str) -> None:
    from app.services.quant_research.scheduler import last_cnhk_session
    from app.services.regime.cnhk import CLOSE_HOUR_UTC, TRIGGER_UTC

    try:
        session_day = last_cnhk_session(datetime.now(UTC), CLOSE_HOUR_UTC[market])
        if is_cnhk_stale(await asyncio.to_thread(_latest_cnhk_date, market), session_day):
            await run_cnhk_once(market, session_day)
        if is_cnhk_stale(await asyncio.to_thread(_latest_cnhk_sector_date, market), session_day):
            await run_cnhk_sector_once(market, session_day)
    except Exception as e:  # noqa: BLE001
        logger.exception("regime_cnhk_bootstrap_failed", market=market, error=str(e))
    hour, minute = TRIGGER_UTC[market]
    while True:
        now = datetime.now(UTC)
        trigger = next_trigger(now, hour, minute, {0, 1, 2, 3, 4})
        await asyncio.sleep(max(0.0, (trigger - now).total_seconds()))
        await run_cnhk_once(market, trigger.date())
        await run_cnhk_sector_once(market, trigger.date())


async def run_cnhk_regime_scheduler() -> None:
    """A 股 / 港股大盘状态调度：启动补跑 + 每个工作日收盘后重算（两个市场各一个循环，错开启动）。"""
    await asyncio.sleep(_STARTUP_DELAY_SECONDS + 30)
    await asyncio.gather(_cnhk_market_loop("cn"), _cnhk_market_loop("hk"))
