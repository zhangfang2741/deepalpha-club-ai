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
from app.schemas.valuation import ETFPricePoint, ETFPriceResponse, ETFValuationDetail, ETFValuationSummaryResponse, GICSValuationResponse, SectorValuationResponse
from app.services.valuation.sector_pe import compute_sector_valuations
from app.services.valuation.etf_pe import compute_etf_valuation_detail, compute_etf_valuation_summary
from app.services.valuation.gics_pe import compute_gics_valuations

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


_ETF_SUMMARY_CACHE_KEY = "valuation:etf-summary-v2"
_ETF_SUMMARY_TTL = 14400  # 4h
_ETF_DETAIL_TTL = 14400   # 4h


@router.get("/etf-summary", response_model=ETFValuationSummaryResponse)
async def get_etf_valuation_summary(
    redis: Redis = Depends(get_redis),
) -> ETFValuationSummaryResponse:
    """获取所有热力图 ETF 的 PE z-score 摘要（冷启动约 10s，之后 4h 缓存）。"""
    try:
        raw = await redis.get(_ETF_SUMMARY_CACHE_KEY)
        if raw:
            payload = json.loads(zlib.decompress(raw))
            return ETFValuationSummaryResponse(**payload)
    except Exception:
        pass

    t0 = time.perf_counter()
    data = await compute_etf_valuation_summary()
    elapsed = (time.perf_counter() - t0) * 1000
    logger.info("etf_summary_computed", ms=round(elapsed, 1), etfs=len(data.etfs))

    if data.etfs:
        try:
            compressed = zlib.compress(data.model_dump_json().encode())
            await redis.set(_ETF_SUMMARY_CACHE_KEY, compressed, ex=_ETF_SUMMARY_TTL)
        except Exception:
            pass

    return data


@router.get("/etf-detail", response_model=ETFValuationDetail)
async def get_etf_valuation_detail(
    symbol: Annotated[str, Query(min_length=1, max_length=10)],
    redis: Redis = Depends(get_redis),
) -> ETFValuationDetail:
    """获取单个 ETF 的完整季度 PE 历史（用于详情图表）。"""
    sym = symbol.upper()
    cache_key = f"valuation:etf-detail-v2:{sym}"

    try:
        raw = await redis.get(cache_key)
        if raw:
            payload = json.loads(zlib.decompress(raw))
            return ETFValuationDetail(**payload)
    except Exception:
        pass

    data = await compute_etf_valuation_detail(sym)

    if data.hist_pe:
        try:
            compressed = zlib.compress(data.model_dump_json().encode())
            await redis.set(cache_key, compressed, ex=_ETF_DETAIL_TTL)
        except Exception:
            pass

    return data


_GICS_CACHE_KEY = "valuation:gics-v6"
_GICS_CACHE_TTL = 14400  # 4h


@router.get("/gics", response_model=GICSValuationResponse)
async def get_gics_valuations(
    redis: Redis = Depends(get_redis),
) -> GICSValuationResponse:
    """获取 GICS 两层行业 PE z-score 估值（一级板块 + 细粒度行业）。

    冷启动约 15 秒（40 次 API 调用），之后 4h 缓存。
    """
    try:
        raw = await redis.get(_GICS_CACHE_KEY)
        if raw:
            payload = json.loads(zlib.decompress(raw))
            return GICSValuationResponse(**payload)
    except Exception:
        pass

    t0 = time.perf_counter()
    data = await compute_gics_valuations()
    elapsed = (time.perf_counter() - t0) * 1000
    logger.info("gics_valuations_computed", ms=round(elapsed, 1), sectors=len(data.sectors))

    if data.sectors:
        try:
            compressed = zlib.compress(data.model_dump_json().encode())
            await redis.set(_GICS_CACHE_KEY, compressed, ex=_GICS_CACHE_TTL)
        except Exception:
            pass

    return data


@router.get("/fmp-probe")
async def probe_fmp_api() -> dict:
    """诊断端点：直接调用 FMP v4 sector PE，返回原始响应（前 3 条），用于排查 API key / 响应格式问题。"""
    from app.core.config import settings
    from app.services.valuation.sector_pe import _quarter_end_dates

    dt = _quarter_end_dates(years=1)[0]  # 最近季度末
    result: dict = {"date_queried": dt, "api_key_suffix": ""}

    if settings.FMP_API_KEY:
        result["api_key_suffix"] = f"...{settings.FMP_API_KEY[-4:]}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://financialmodelingprep.com/api/v4/sector_price_earning_ratio",
                params={"date": dt, "apikey": settings.FMP_API_KEY},
            )
            result["status_code"] = resp.status_code
            try:
                body = resp.json()
                result["response_type"] = type(body).__name__
                if isinstance(body, list):
                    result["record_count"] = len(body)
                    result["sample"] = body[:3]
                else:
                    result["body"] = body
            except Exception:
                result["raw_body"] = resp.text[:500]
    except Exception as e:
        result["error"] = str(e)

    return result
