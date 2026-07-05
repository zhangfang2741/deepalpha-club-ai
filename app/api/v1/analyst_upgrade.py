"""分析师目标价持续上调 API 端点."""

import json
import zlib
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from redis.asyncio import Redis

from app.cache.client import get_redis_optional
from app.core.logging import logger
from app.schemas.analyst_upgrade import (
    Nasdaq100UpgradesResponse,
    PriceTargetHistoryResponse,
    SP500UpgradesResponse,
)
from app.services.analyst_upgrade.nasdaq100 import (
    compute_custom_price_target_history,
    compute_nasdaq100_upgrades,
    compute_price_target_history,
)
from app.services.analyst_upgrade.sp500 import compute_sp500_upgrades

router = APIRouter()

_UPGRADES_CACHE_KEY = "analyst_upgrade:nasdaq100:v3"
_SP500_CACHE_KEY = "analyst_upgrade:sp500:v5"
_UPGRADES_TTL = 21600   # 6h
_SP500_TTL = 21600      # 6h
_HISTORY_TTL = 43200    # 12h


def _history_cache_key(symbol: str) -> str:
    return f"analyst_upgrade:history:{symbol.upper()}:v1"


def _custom_history_cache_key(symbol: str, start: date, end: date) -> str:
    return f"analyst_upgrade:history:custom:{symbol.upper()}:{start.isoformat()}:{end.isoformat()}:v1"


@router.get("/nasdaq100", response_model=Nasdaq100UpgradesResponse)
async def get_nasdaq100_upgrades(
    redis: Redis | None = Depends(get_redis_optional),
    refresh: Annotated[bool, Query(description="为 true 时跳过缓存，强制重新计算")] = False,
) -> Nasdaq100UpgradesResponse:
    """返回纳斯达克 100 中分析师目标价持续上调的股票列表（月均>季均>年均）.

    冷启动约 15 秒（100 次并发 FMP 请求），之后 6h 缓存。
    传 ?refresh=true 可跳过缓存强制刷新。
    """
    if not refresh:
        if redis:
            try:
                raw = await redis.get(_UPGRADES_CACHE_KEY)
                if raw:
                    return Nasdaq100UpgradesResponse(**json.loads(zlib.decompress(raw)))
            except Exception:
                pass

    data = await compute_nasdaq100_upgrades()

    if data.stocks:
        if redis:
            try:
                compressed = zlib.compress(data.model_dump_json().encode())
                await redis.set(_UPGRADES_CACHE_KEY, compressed, ex=_UPGRADES_TTL)
            except Exception:
                pass

    logger.info("nasdaq100_upgrades_served", count=data.upgrade_count)
    return data


@router.get("/sp500", response_model=SP500UpgradesResponse)
async def get_sp500_upgrades(
    redis: Redis | None = Depends(get_redis_optional),
    refresh: Annotated[bool, Query(description="为 true 时跳过缓存，强制重新计算")] = False,
) -> SP500UpgradesResponse:
    """返回标普 500 中分析师目标价持续上调的股票列表（月均>季均>年均）.

    冷启动约 75 秒（500 次并发 FMP 请求），之后 6h 缓存。
    传 ?refresh=true 可跳过缓存强制刷新。
    """
    if not refresh:
        if redis:
            try:
                raw = await redis.get(_SP500_CACHE_KEY)
                if raw:
                    return SP500UpgradesResponse(**json.loads(zlib.decompress(raw)))
            except Exception:
                pass

    data = await compute_sp500_upgrades()

    if data.stocks:
        if redis:
            try:
                compressed = zlib.compress(data.model_dump_json().encode())
                await redis.set(_SP500_CACHE_KEY, compressed, ex=_SP500_TTL)
            except Exception:
                pass

    logger.info("sp500_upgrades_served", count=data.upgrade_count)
    return data


@router.get("/price-target-history/{symbol}", response_model=PriceTargetHistoryResponse)
async def get_price_target_history(
    symbol: Annotated[str, Path(min_length=1, max_length=10)],
    redis: Redis | None = Depends(get_redis_optional),
) -> PriceTargetHistoryResponse:
    """返回个股近 5 年按月聚合的分析师平均目标价（用于折线图）."""
    sym = symbol.upper()
    cache_key = _history_cache_key(sym)

    if redis:
        try:
            raw = await redis.get(cache_key)
            if raw:
                return PriceTargetHistoryResponse(**json.loads(zlib.decompress(raw)))
        except Exception:
            pass

    data = await compute_price_target_history(sym)

    if data.points:
        if redis:
            try:
                compressed = zlib.compress(data.model_dump_json().encode())
                await redis.set(cache_key, compressed, ex=_HISTORY_TTL)
            except Exception:
                pass

    logger.info("price_target_history_served", symbol=sym, months=len(data.points))
    return data


@router.get("/custom-price-target", response_model=PriceTargetHistoryResponse)
async def get_custom_price_target(
    symbol: Annotated[str, Query(min_length=1, max_length=10, description="美股股票代码，如 AAPL")],
    start: Annotated[date, Query(description="起始日期（含），格式 YYYY-MM-DD")],
    end: Annotated[date, Query(description="结束日期（含），格式 YYYY-MM-DD")],
    redis: Redis | None = Depends(get_redis_optional),
    refresh: Annotated[bool, Query(description="为 true 时跳过缓存，强制重新计算")] = False,
) -> PriceTargetHistoryResponse:
    """返回个股在自定义时间区间内按月聚合的分析师平均目标价（用于自定义查询 Tab）."""
    if start > end:
        raise HTTPException(status_code=400, detail="起始日期不能晚于结束日期")

    sym = symbol.upper()
    cache_key = _custom_history_cache_key(sym, start, end)

    if not refresh:
        if redis:
            try:
                raw = await redis.get(cache_key)
                if raw:
                    return PriceTargetHistoryResponse(**json.loads(zlib.decompress(raw)))
            except Exception:
                pass

    data = await compute_custom_price_target_history(sym, start, end)

    if data.points:
        if redis:
            try:
                compressed = zlib.compress(data.model_dump_json().encode())
                await redis.set(cache_key, compressed, ex=_HISTORY_TTL)
            except Exception:
                pass

    logger.info(
        "custom_price_target_served",
        symbol=sym,
        start=start.isoformat(),
        end=end.isoformat(),
        months=len(data.points),
    )
    return data
