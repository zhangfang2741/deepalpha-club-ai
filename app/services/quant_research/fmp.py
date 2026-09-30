"""量化研究用到的 FMP 端点。每次调用前经全局预算（app/cache/fmp_budget）限流。

数据来源只进日志，不进响应。失败返回 None，由调用方决定沿用旧数据还是标缺失。
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import httpx
from redis.asyncio import Redis

from app.cache.fmp_budget import Priority, acquire, report_429
from app.core.config import settings
from app.core.logging import logger

BASE = "https://financialmodelingprep.com/stable"
MAX_ATTEMPTS = 4


class FmpClient:
    def __init__(self, client: httpx.AsyncClient, redis: Redis | None, priority: Priority):
        """按 priority 决定走用户额度还是批量额度。"""
        self.client = client
        self.redis = redis
        self.priority: Priority = priority

    async def get(self, path: str, **params) -> list | dict | None:
        if not settings.FMP_API_KEY:
            return None
        params["apikey"] = settings.FMP_API_KEY
        for attempt in range(MAX_ATTEMPTS):
            await acquire(self.redis, self.priority)
            try:
                resp = await self.client.get(f"{BASE}/{path}", params=params, timeout=30)
            except httpx.HTTPError as e:
                logger.warning("quant_fmp_request_error", path=path, attempt=attempt, error=str(e))
                await asyncio.sleep(2 * (attempt + 1))
                continue
            if resp.status_code == 429:
                await report_429(self.redis, self.priority)
                await asyncio.sleep(5 * (attempt + 1))
                continue
            if resp.status_code != 200:
                logger.warning("quant_fmp_http_error", path=path, status=resp.status_code,
                               symbol=params.get("symbol"))
                return None
            try:
                return resp.json()
            except ValueError:
                logger.warning("quant_fmp_bad_json", path=path, symbol=params.get("symbol"))
                return None
        return None

    async def income_quarters(self, symbol: str, limit: int = 16):
        return await self.get("income-statement", symbol=symbol, period="quarter", limit=limit)

    async def cash_quarters(self, symbol: str, limit: int = 8):
        return await self.get("cash-flow-statement", symbol=symbol, period="quarter", limit=limit)

    async def balance_latest(self, symbol: str):
        return await self.get("balance-sheet-statement", symbol=symbol, period="quarter", limit=1)

    async def estimates_annual(self, symbol: str):
        return await self.get("analyst-estimates", symbol=symbol, period="annual", limit=10)

    async def price_light(self, symbol: str, as_of: date, days: int = 420):
        return await self.get("historical-price-eod/light", symbol=symbol,
                              **{"from": (as_of - timedelta(days=days)).isoformat()})

    async def profile(self, symbol: str):
        return await self.get("profile", symbol=symbol)

    async def earnings_calendar(self, start: date, end: date):
        return await self.get("earnings-calendar", **{"from": start.isoformat(), "to": end.isoformat()})
