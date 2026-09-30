"""个股分析师评级概览：并发拉取 6 个 FMP 端点（经全局预算，priority=user）+ Redis 缓存。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
from redis.asyncio import Redis

from app.cache.operations import get_json, set_json
from app.core.logging import logger
from app.schemas.analyst_upgrade import AnalystOverviewOut
from app.services.analyst_upgrade.overview import Lang, build_overview
from app.services.quant_research.fmp import FmpClient

CACHE_TTL = 6 * 3600


def cache_key(symbol: str, lang: str) -> str:
    """缓存键（带版本号，结构变动时升版本）。"""
    return f"analyst_upgrade:overview:v1:{symbol}:{lang}"


async def get_analyst_overview(symbol: str, lang: Lang, *, redis: Redis | None) -> AnalystOverviewOut:
    """缓存 → 并发拉取 → 整理。"""
    symbol = symbol.upper()
    key = cache_key(symbol, lang)
    if redis is not None:
        try:
            cached = await get_json(redis, key)
            if cached:
                return AnalystOverviewOut(**cached)
        except Exception as e:  # noqa: BLE001
            logger.warning("analyst_overview_cache_read_failed", symbol=symbol, error=str(e))

    async with httpx.AsyncClient() as client:
        fmp = FmpClient(client, redis, "user")
        hist, ptc, pts, earnings, grades, quote = await asyncio.gather(
            fmp.get("grades-historical", symbol=symbol, limit=12),
            fmp.get("price-target-consensus", symbol=symbol),
            fmp.get("price-target-summary", symbol=symbol),
            fmp.get("earnings", symbol=symbol, limit=8),
            fmp.get("grades", symbol=symbol, limit=20),
            fmp.get("quote-short", symbol=symbol),
        )
    out = build_overview(symbol, lang, datetime.now(UTC).date(), hist=hist, ptc=ptc, pts=pts,
                         earnings=earnings, grades=grades, quote=quote)
    if out.status == "ok" and redis is not None:
        try:
            await set_json(redis, key, out.model_dump(mode="json"), expire=CACHE_TTL)
        except Exception as e:  # noqa: BLE001
            logger.warning("analyst_overview_cache_write_failed", symbol=symbol, error=str(e))
    logger.info("analyst_overview_built", symbol=symbol, status=out.status)
    return out
