"""美股 symbol 联想搜索（FMP 转发 + Redis 缓存）"""
from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

import httpx
from redis.asyncio import Redis

from app.cache.operations import get_json, set_json
from app.core.logging import logger

_FMP_KEY = os.environ.get("FMP_API_KEY", "")
_FMP_SEARCH_URL = "https://financialmodelingprep.com/stable/search-symbol"
_CACHE_TTL = 3600 * 24  # 24h
_US_EXCHANGES = {"NASDAQ", "NYSE", "AMEX", "BATS", "NYSE ARCA"}


async def search_us_symbols(
    query: str,
    *,
    redis: Redis | None = None,
    limit: int = 10,
) -> list[dict]:
    """按关键词搜索美股 symbol，过滤主流交易所。

    返回 list[{symbol, name, exchange}]，最多 limit 条。
    """
    q = query.strip()
    if not q:
        return []

    cache_key = f"skill_symbol_search:us:{q.lower()}:{limit}"
    if redis:
        cached = await get_json(redis, cache_key)
        if cached is not None:
            logger.debug("symbol_search_cache_hit", query=q)
            return cached

    results = await _fetch_fmp_search(q, limit * 3)
    filtered = [
        {"symbol": r["symbol"], "name": r.get("name", ""), "exchange": r.get("exchange", "")}
        for r in results
        if r.get("exchange") in _US_EXCHANGES
    ][:limit]

    if redis:
        await set_json(redis, cache_key, filtered, expire=_CACHE_TTL)

    logger.info("symbol_search_done", query=q, count=len(filtered))
    return filtered


async def _fetch_fmp_search(query: str, limit: int) -> list[dict]:
    def _sync():
        resp = httpx.get(
            _FMP_SEARCH_URL,
            params={"query": query, "limit": limit, "apikey": _FMP_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        return await loop.run_in_executor(pool, _sync)
