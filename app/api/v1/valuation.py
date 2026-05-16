"""行业估值热度 API 端点。"""

import time

from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.cache.client import get_redis
from app.cache.valuation_cache import get_valuation_cache, set_valuation_cache
from app.core.logging import logger
from app.schemas.valuation import SectorValuationResponse
from app.services.valuation.sector_pe import compute_sector_valuations

router = APIRouter()


@router.get("/sectors", response_model=SectorValuationResponse)
async def get_sector_valuations(
    redis: Redis = Depends(get_redis),
) -> SectorValuationResponse:
    """获取各 GICS 行业过去 10 年 PE 的 z-score 估值热度。

    数据来源：FMP v4 /sector_price_earning_ratio
    估值分级：极度低估 / 低估 / 中性 / 高估 / 极度高估（±1σ / ±2σ）
    """
    t0 = time.perf_counter()
    cached = await get_valuation_cache(redis)
    if cached is not None:
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("sector_valuation_cache_hit", cache_read_ms=round(elapsed, 1))
        return cached

    logger.info("sector_valuation_cache_miss")
    t1 = time.perf_counter()
    data = await compute_sector_valuations()
    compute_ms = (time.perf_counter() - t1) * 1000

    if not data.sectors:
        logger.warning("sector_valuation_empty")
        return data

    await set_valuation_cache(redis, data)
    total_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "sector_valuation_cache_set_complete",
        sectors=len(data.sectors),
        compute_ms=round(compute_ms, 1),
        total_ms=round(total_ms, 1),
    )
    return data
