"""宏观驱动因素与日历的取数（美股）。所有调用经 FMP 全局预算限流（FmpClient → fmp_budget.acquire）。

失败的单个因素返回空序列（drivers.evaluate_driver 会标「暂无数据」），不影响其他因素。
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta

import httpx
from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import logger
from app.services.quant_research.fmp import FmpClient

_LOOKBACK_DAYS = 70  # 日历天，覆盖 20 个交易日窗口 + 节假日余量

# 美元 / 原油用跟踪基金近似（只算涨跌幅）
_PRICE_SYMBOLS = {"vix": "^VIX", "dollar": "UUP", "oil": "USO"}

Series = list[tuple[str, float]]


def _price_series(body: list | dict | None) -> Series:
    if not isinstance(body, list):
        return []
    pts = [(str(r["date"]), float(r["price"])) for r in body if r.get("date") and r.get("price") is not None]
    pts.sort()
    return pts


def treasury_series(body: list | dict | None) -> tuple[Series, Series]:
    """treasury-rates 原始响应 → (10 年期序列, 10Y-2Y 利差序列)，按日期升序。"""
    if not isinstance(body, list):
        return [], []
    y10: Series = []
    curve: Series = []
    for r in body:
        d, ten, two = r.get("date"), r.get("year10"), r.get("year2")
        if not d or ten is None:
            continue
        y10.append((str(d), float(ten)))
        if two is not None:
            curve.append((str(d), round(float(ten) - float(two), 4)))
    y10.sort()
    curve.sort()
    return y10, curve


async def fetch_us_driver_series(redis: Redis | None, today: date) -> dict[str, Series]:
    """拉美股 5 个驱动因素近 70 天的序列。"""
    start = (today - timedelta(days=_LOOKBACK_DAYS)).isoformat()
    async with httpx.AsyncClient(proxy=settings.HTTP_PROXY or settings.HTTPS_PROXY or None) as client:
        fmp = FmpClient(client, redis, "user")
        treasury, *prices = await asyncio.gather(
            fmp.get("treasury-rates", **{"from": start, "to": today.isoformat()}),
            *(fmp.get("historical-price-eod/light", symbol=sym, **{"from": start})
              for sym in _PRICE_SYMBOLS.values()),
        )
    y10, curve = treasury_series(treasury)
    out: dict[str, Series] = {"us10y": y10, "curve": curve}
    for key, body in zip(_PRICE_SYMBOLS, prices, strict=True):
        out[key] = _price_series(body)
    logger.info("macro_us_series_fetched", lengths={k: len(v) for k, v in out.items()})
    return out


async def fetch_calendar(redis: Redis | None, today: date, days: int = 8) -> list[dict]:
    """拉未来 days 天的宏观日历原始事件。"""
    async with httpx.AsyncClient(proxy=settings.HTTP_PROXY or settings.HTTPS_PROXY or None) as client:
        body = await FmpClient(client, redis, "user").get(
            "economic-calendar", **{"from": today.isoformat(), "to": (today + timedelta(days=days)).isoformat()})
    return body if isinstance(body, list) else []
