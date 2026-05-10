"""ETF 资金流热力图 API 端点。"""

import time
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis

from app.cache.client import get_redis
from app.cache.etf_cache import get_heatmap_cache, set_heatmap_cache
from app.core.logging import logger
from app.schemas.etf import CandleResponse, HeatmapResponse
from app.services.etf.fetcher import build_heatmap_data, fetch_candles

router = APIRouter()

# 缓存 TTL: 1小时（与 Redis TTL 保持一致）
CACHE_MAX_AGE = 3600


@router.get("/heatmap", response_model=HeatmapResponse)
async def get_etf_heatmap(
    granularity: Annotated[str, Query(pattern="^(day|week|month)$")] = "day",
    days: Annotated[int, Query(ge=5, le=700)] = 30,
    redis: Redis = Depends(get_redis),
) -> HeatmapResponse:
    """获取 ETF 资金流热力图数据。

    - granularity: 粒度，day | week | month
    - days: 交易日数量（day=30, week=150, month=630），默认 30
    """
    t0 = time.perf_counter()
    cached = await get_heatmap_cache(redis, granularity, days)
    if cached is not None:
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("etf_heatmap_cache_hit", granularity=granularity, days=days, cache_read_ms=round(elapsed, 1))
        return cached

    t1 = time.perf_counter()
    logger.info("etf_heatmap_cache_miss", granularity=granularity, days=days)
    data = build_heatmap_data(granularity=granularity, days=days)
    build_ms = (time.perf_counter() - t1) * 1000
    
    # 数据为空时不写缓存，避免缓存空数据
    if not data.sectors or all(len(s.etfs) == 0 for s in data.sectors):
        logger.warning("etf_heatmap_empty_data", granularity=granularity, days=days, build_ms=round(build_ms, 1))
        return data
    
    await set_heatmap_cache(redis, granularity, days, data)
    total_ms = (time.perf_counter() - t0) * 1000
    logger.info("etf_heatmap_cache_set_complete", granularity=granularity, days=days, build_ms=round(build_ms, 1), total_ms=round(total_ms, 1))
    return data


@router.get("/{symbol}/candles", response_model=CandleResponse)
async def get_etf_candles(
    symbol: str,
    granularity: Annotated[str, Query(pattern="^(day|week|month)$")] = "day",
) -> CandleResponse:
    """获取单只 ETF K 线数据（日/周/月）。"""
    return fetch_candles(symbol.upper(), granularity=granularity)
