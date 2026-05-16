"""行业估值热度 API 端点。"""

import json
import time
import zlib
from datetime import date, timedelta
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis

from app.cache.client import get_redis
from app.cache.valuation_cache import get_valuation_cache, set_valuation_cache
from app.core.logging import logger
from app.schemas.valuation import ETFPricePoint, ETFPriceResponse, SectorValuationResponse
from app.services.valuation.sector_pe import compute_sector_valuations

router = APIRouter()

_ETF_PRICE_TTL = 7200  # 2h


def _etf_price_cache_key(symbol: str, days: int) -> str:
    return f"valuation:etf-price:{symbol.upper()}:{days}"


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


@router.get("/etf-price", response_model=ETFPriceResponse)
async def get_etf_price(
    symbol: Annotated[str, Query(min_length=1, max_length=10)],
    days: Annotated[int, Query(ge=30, le=1825)] = 730,
    redis: Redis = Depends(get_redis),
) -> ETFPriceResponse:
    """获取指定 ETF 的历史收盘价（用于行业估值详情图表）。"""
    from app.core.config import settings

    sym = symbol.upper()
    cache_key = _etf_price_cache_key(sym, days)

    # 尝试缓存
    try:
        raw = await redis.get(cache_key)
        if raw:
            payload = json.loads(zlib.decompress(raw))
            return ETFPriceResponse(**payload)
    except Exception:
        pass

    # 拉取 FMP stable historical-price-eod
    to_date = date.today().strftime("%Y-%m-%d")
    from_date = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")

    prices: list[ETFPricePoint] = []
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://financialmodelingprep.com/stable/historical-price-eod/full",
                params={"symbol": sym, "from": from_date, "to": to_date, "apikey": settings.FMP_API_KEY},
            )
            if resp.status_code == 200:
                data = resp.json()
                # stable API 返回列表
                records = data if isinstance(data, list) else data.get("historical", [])
                for rec in records:
                    dt = rec.get("date") or rec.get("Date")
                    close = rec.get("close") or rec.get("Close")
                    if dt and close and float(close) > 0:
                        prices.append(ETFPricePoint(date=dt, close=round(float(close), 4)))
                # 按日期升序
                prices.sort(key=lambda p: p.date)
            else:
                logger.warning("etf_price_fetch_error", symbol=sym, status=resp.status_code)
    except Exception as e:
        logger.warning("etf_price_fetch_failed", symbol=sym, error=str(e))

    result = ETFPriceResponse(symbol=sym, prices=prices)

    # 写缓存（仅当有数据时）
    if prices:
        try:
            compressed = zlib.compress(result.model_dump_json().encode())
            await redis.set(cache_key, compressed, ex=_ETF_PRICE_TTL)
        except Exception:
            pass

    return result
