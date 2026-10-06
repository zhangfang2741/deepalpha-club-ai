"""个股分析师评级概览（Redis 缓存 6 小时）。

美股并发拉取 6 个 FMP 端点（经全局预算，priority=user）；A 股取 F10 评级统计与研报列表，港股取券商预测页。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
from redis.asyncio import Redis

from app.cache.operations import get_json, set_json
from app.core.logging import logger
from app.schemas.analyst_upgrade import AnalystOverviewOut
from app.services.analyst_upgrade.overview import Lang, build_overview
from app.services.analyst_upgrade.overview_cnhk import build_cn_overview, build_hk_overview
from app.services.quant_research.cnhk import eastmoney as em
from app.services.quant_research.cnhk import etnet
from app.services.quant_research.cnhk.http import new_client
from app.services.quant_research.cnhk.pipeline import fetch_prices
from app.services.quant_research.fmp import FmpClient
from app.services.quant_research.markets import normalize_symbol

CACHE_TTL = 6 * 3600


def cache_key(symbol: str, lang: str, market: str = "us") -> str:
    """缓存键（带版本号，结构变动时升版本）。美股键保持原样。"""
    if market != "us":
        return f"analyst_upgrade:overview:v1:{market}:{symbol}:{lang}"
    return f"analyst_upgrade:overview:v2:{symbol}:{lang}"


async def get_analyst_overview(symbol: str, lang: Lang, *, redis: Redis | None,
                               market: str = "us") -> AnalystOverviewOut:
    """缓存 → 并发拉取 → 整理。"""
    symbol = normalize_symbol(market, symbol)
    key = cache_key(symbol, lang, market)
    if redis is not None:
        try:
            cached = await get_json(redis, key)
            if cached:
                return AnalystOverviewOut(**cached)
        except Exception as e:  # noqa: BLE001
            logger.warning("analyst_overview_cache_read_failed", symbol=symbol, error=str(e))

    if market != "us":
        out = await _build_cnhk(market, symbol, lang, redis)
        await _store(redis, key, out)
        return out

    async with httpx.AsyncClient() as client:
        fmp = FmpClient(client, redis, "user")
        hist, ptc, pts, earnings, grades, quote, grades_news = await asyncio.gather(
            fmp.get("grades-historical", symbol=symbol, limit=12),
            fmp.get("price-target-consensus", symbol=symbol),
            fmp.get("price-target-summary", symbol=symbol),
            fmp.get("earnings", symbol=symbol, limit=8),
            fmp.get("grades", symbol=symbol, limit=20),
            fmp.get("quote-short", symbol=symbol),
            fmp.get("grades-news", symbol=symbol, limit=50),  # 评级变动对应的媒体报道；失败 / 套餐不含时为空，不影响其他区块
        )
    out = build_overview(symbol, lang, datetime.now(UTC).date(), hist=hist, ptc=ptc, pts=pts,
                         earnings=earnings, grades=grades, quote=quote, grades_news=grades_news)
    await _store(redis, key, out)
    logger.info("analyst_overview_built", symbol=symbol, status=out.status,
                news_rows=len(grades_news) if isinstance(grades_news, list) else None,
                news_linked=sum(1 for g in out.recent_grades if g.report_url))
    return out


async def _store(redis: Redis | None, key: str, out: AnalystOverviewOut) -> None:
    if out.status == "ok" and redis is not None:
        try:
            await set_json(redis, key, out.model_dump(mode="json"), expire=CACHE_TTL)
        except Exception as e:  # noqa: BLE001
            logger.warning("analyst_overview_cache_write_failed", key=key, error=str(e))


async def _build_cnhk(market: str, symbol: str, lang: Lang, redis: Redis | None) -> AnalystOverviewOut:
    """A 股：近 18 个月研报（每个月末回看 6 个月的评级分布需要）；港股：券商预测页。"""
    today = datetime.now(UTC).date()
    prices = await fetch_prices(symbol, today, redis)
    price = prices[-1]["price"] if prices else None
    async with new_client() as client:
        if market == "cn":
            reports, f10 = await asyncio.gather(
                em.research_reports(client, symbol, today - timedelta(days=548), today), em.f10_forecast(client, symbol))
            out = build_cn_overview(symbol, lang, today, reports, price, f10)
        else:
            html = await etnet.fetch(client, symbol)
            out = build_hk_overview(symbol, lang, today, etnet.parse(html) if html else None, price)
    logger.info("analyst_overview_built", market=market, symbol=symbol, status=out.status)
    return out
