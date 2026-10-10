"""基本面雷达 / 评级雷达的后台预热：用户请求只读缓存，慢活（读库、算 90 天评级升降、拉券商数据）都在这里提前做完。

每小时巡检一轮（启动后先跑一轮）：对每个预热市场的每个指数，
- 基本面雷达：算出 `get_trend_radar` 的结果写进 Redis（新一天批量后键换新，旧的自然过期）；
- 评级雷达（仅美股）：`cached_analyst_radar(refresh=True)` 重算并写回，同时触发缺失 / 过期券商数据的后台补拉。
自选因人而异，不预热。
"""
from __future__ import annotations

import asyncio

from app.cache.client import current_redis
from app.core.logging import logger
from app.services.quant_research.markets import normalize_symbol
from app.services.quant_research.trend_radar import get_trend_radar
from app.services.signal_radar import analyst_events as ae
from app.services.signal_radar.analyst_radar import cached_analyst_radar
from app.services.signal_radar.constituents import resolve_constituents
from app.services.signal_radar.universe import all_universes

_INTERVAL_SECONDS = 3600


async def warm_trend_radars_once() -> None:
    """把所有预热指数的基本面雷达 / 评级雷达算一遍写进缓存（单个失败不影响其它）。"""
    redis = current_redis()
    if redis is None:
        return
    for u in all_universes():
        try:
            pairs = await resolve_constituents(u.market, redis=redis, universe_key=u.key)
            if not pairs:
                continue
            members = {normalize_symbol(u.market, s) for s, _ in pairs}
            await get_trend_radar(u.market, "zh", redis=redis, members=members, scope=u.key)
            if u.market in ae.SUPPORTED_MARKETS:
                await cached_analyst_radar(u.market, list(pairs), u.key, redis=redis, refresh=True)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 单个指数失败不影响其它
            logger.warning("trend_radar_warm_failed", market=u.market, universe=u.key, error=str(e))
    logger.info("trend_radar_warm_done")


async def trend_warm_loop() -> None:
    """启动后立即预热一轮，之后每小时一轮。"""
    while True:
        try:
            await warm_trend_radars_once()
            await asyncio.sleep(_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("trend_radar_warm_loop_failed", error=str(e))
            await asyncio.sleep(_INTERVAL_SECONDS)
