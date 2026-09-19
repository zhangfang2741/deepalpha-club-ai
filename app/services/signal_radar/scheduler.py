"""信号雷达进程内定时预热调度。

在 API 进程存活期间，周期性地为各市场跑一次全量扫描并写入 Redis 缓存，
让用户进「信号」Tab 直接命中缓存，而不是首访时触发数十只缠论的慢扫描。
默认 6h 一轮，与缓存 TTL 对齐。用 SIGNAL_RADAR_PREWARM_ENABLED 开关。
"""
from __future__ import annotations

import asyncio

from app.cache.client import current_redis
from app.core.config import settings
from app.core.logging import logger
from app.services.signal_radar.service import compute_market

# 启动后先等一会儿再首扫，避开启动期其它预热任务抢资源。
_STARTUP_DELAY_SECONDS = 45


async def _prewarm_once() -> None:
    redis = current_redis()
    if redis is None:
        logger.warning("signal_radar_prewarm_no_redis")
        return
    for market in settings.SIGNAL_RADAR_PREWARM_MARKETS:
        try:
            resp = await compute_market(market, redis=redis, user_id=None)
            logger.info("signal_radar_prewarmed", market=market, days=len(resp.days))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 单个市场失败不影响其余
            logger.exception("signal_radar_prewarm_market_failed", market=market, error=str(e))


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
