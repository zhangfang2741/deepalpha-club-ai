"""信号雷达进程内定时预热调度。

在 API 进程存活期间，周期性地为各市场跑一次全量扫描并写入 Redis 缓存，
让用户进「信号」Tab 直接命中缓存，而不是首访时触发数十只缠论的慢扫描。
默认 6h 一轮，与缓存 TTL 对齐。用 SIGNAL_RADAR_PREWARM_ENABLED 开关。
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.cache.client import current_redis
from app.core.config import settings
from app.core.logging import logger
from app.services.signal_radar.service import compute_market, market_session_active, refresh_sub_levels
from app.services.signal_radar.universe import all_universes

# 启动后先等一会儿再首扫，避开启动期其它预热任务抢资源。
_STARTUP_DELAY_SECONDS = 45


async def _prewarm_once() -> None:
    redis = current_redis()
    if redis is None:
        logger.warning("signal_radar_prewarm_no_redis")
        return
    markets = set(settings.SIGNAL_RADAR_PREWARM_MARKETS)
    prewarm_broad = settings.SIGNAL_RADAR_PREWARM_BROAD_ENABLED
    # 遍历所有 (市场, universe)。串行执行：大盘宽基成分多，避免多套扫描并发抢数据源。
    for u in all_universes():
        if u.market not in markets:
            continue
        # 非默认（大盘宽基）universe 由独立开关控制，关掉则跳过、走首访按需扫。
        if not u.is_default and not prewarm_broad:
            continue
        try:
            resp = await compute_market(
                u.market, redis=redis, user_id=None, universe_key=u.key
            )
            logger.info(
                "signal_radar_prewarmed", market=u.market, universe=u.key, days=len(resp.days)
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 单个 universe 失败不影响其余
            logger.exception(
                "signal_radar_prewarm_market_failed", market=u.market, universe=u.key, error=str(e)
            )


def _target_universes() -> list:
    """预热覆盖的 (市场, universe)：与全量预热同一范围。"""
    markets = set(settings.SIGNAL_RADAR_PREWARM_MARKETS)
    return [u for u in all_universes()
            if u.market in markets and (u.is_default or settings.SIGNAL_RADAR_PREWARM_BROAD_ENABLED)]


async def _refresh_sub_levels_once() -> None:
    redis = current_redis()
    if redis is None:
        return
    now = datetime.now(UTC)
    for u in _target_universes():
        if not market_session_active(u.market, now):
            continue
        try:
            await refresh_sub_levels(u.market, u.key, redis=redis, now=now)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 单个 universe 失败不影响其余
            logger.exception("signal_radar_sub_level_refresh_failed", market=u.market, universe=u.key,
                             error=str(e))


async def run_signal_radar_sub_level_scheduler() -> None:
    """盘中定时刷新雷达共振标记（次级别结论），直到进程退出。"""
    interval = settings.SIGNAL_RADAR_SUB_LEVEL_REFRESH_SECONDS
    if interval <= 0:
        logger.info("signal_radar_sub_level_refresh_disabled")
        return
    try:
        # 晚于全量首扫启动，首轮通常已有快照可刷
        await asyncio.sleep(_STARTUP_DELAY_SECONDS + interval)
    except asyncio.CancelledError:
        return
    while True:
        try:
            await _refresh_sub_levels_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("signal_radar_sub_level_refresh_loop_failed", error=str(e))
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


async def run_signal_radar_prewarm_scheduler() -> None:
    """周期性预热各市场信号雷达缓存，直到进程退出。"""
    if not settings.SIGNAL_RADAR_PREWARM_ENABLED:
        logger.info("signal_radar_prewarm_disabled")
        return

    try:
        await asyncio.sleep(_STARTUP_DELAY_SECONDS)
    except asyncio.CancelledError:
        return

    while True:
        try:
            await _prewarm_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("signal_radar_prewarm_failed", error=str(e))
        try:
            await asyncio.sleep(settings.SIGNAL_RADAR_PREWARM_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            return
