"""ETF 资金流热力图 API 端点。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis

from app.cache.client import get_redis
from app.cache.etf_cache import get_heatmap_cache, set_heatmap_cache
from app.core.logging import logger
from app.schemas.etf import CandleResponse, HeatmapResponse
from app.services.etf.fetcher import build_heatmap_data, fetch_candles

router = APIRouter()


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
    cached = await get_heatmap_cache(redis, granularity, days)
    if cached is not None:
        logger.info("etf_heatmap_cache_hit", granularity=granularity, days=days)
        return cached

    logger.info("etf_heatmap_cache_miss", granularity=granularity, days=days)
    data = build_heatmap_data(granularity=granularity, days=days)
    await set_heatmap_cache(redis, granularity, days, data)
    return data


@router.get("/{symbol}/candles", response_model=CandleResponse)
async def get_etf_candles(
    symbol: str,
    granularity: Annotated[str, Query(pattern="^(day|week|month)$")] = "day",
) -> CandleResponse:
    """获取单只 ETF K 线数据（日/周/月）。"""
    return fetch_candles(symbol.upper(), granularity=granularity)
