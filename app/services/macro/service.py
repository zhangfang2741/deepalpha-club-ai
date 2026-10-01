"""宏观环境 / 市场概览编排：regime 因子表 + 驱动因素 + 宏观日历 + 宽基雷达按行业统计。

第一期只有美股（MACRO_MARKETS）；A 股 / 港股返回 available=false，App 显示「数据建设中」。
"""
from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

from redis.asyncio import Redis

from app.cache import macro_cache as cache
from app.core.logging import logger
from app.schemas.macro import MacroResponse, MarketOverviewResponse, SectorBoardResponse
from app.services.macro import fetcher, regime_view
from app.services.macro.calendar import filter_events, next_key_event
from app.services.macro.drivers import DRIVERS_BY_MARKET, evaluate_driver

MACRO_MARKETS = frozenset({"us"})


def _today() -> date:
    return datetime.now(UTC).date()


async def _driver_series(redis: Redis | None, market: str) -> dict[str, list[tuple[str, float]]]:
    today = _today()
    key = f"macro:series:{market}:{today.isoformat()}"
    cached = await cache.get_json(redis, key)
    if isinstance(cached, dict):
        return {k: [(d, float(v)) for d, v in pts] for k, pts in cached.items()}
    series = await fetcher.fetch_us_driver_series(redis, today)
    # 全部为空（取数整体失败）不缓存，下次请求重试
    if any(series.values()):
        await cache.set_json(redis, key, series, cache.SERIES_TTL)
    return series


async def _calendar(redis: Redis | None) -> list[dict]:
    today = _today()
    key = f"macro:calendar:{today.isoformat()}"
    cached = await cache.get_json(redis, key)
    if isinstance(cached, list):
        return cached
    raw = await fetcher.fetch_calendar(redis, today)
    if raw:
        await cache.set_json(redis, key, raw, cache.CALENDAR_TTL)
    return raw


async def get_macro(redis: Redis | None, market: str, lang: str = "zh") -> MacroResponse:
    """宏观弹层。"""
    if market not in MACRO_MARKETS:
        return MacroResponse(market=market, available=False)
    key = f"macro:resp:{market}:{lang}"
    if (hit := await cache.get_model(redis, key, MacroResponse)) is not None:
        return hit
    rows, series, raw_events = await asyncio.gather(
        asyncio.to_thread(regime_view.load_state_rows), _driver_series(redis, market), _calendar(redis))
    resp = MacroResponse(
        market=market,
        available=True,
        state=regime_view.build_state(rows, lang),
        history=regime_view.state_history(rows),
        drivers=[evaluate_driver(spec, series.get(spec.key, []), lang) for spec in DRIVERS_BY_MARKET[market]],
        events=filter_events(raw_events, market, datetime.now(UTC), lang),
    )
    if resp.state is not None:
        await cache.set_model(redis, key, resp)
    logger.info("macro_response_built", market=market, has_state=resp.state is not None,
                events=len(resp.events))
    return resp


async def get_overview(redis: Redis | None, market: str, lang: str = "zh") -> MarketOverviewResponse:
    """顶部宏观格 + 行业格摘要。"""
    if market not in MACRO_MARKETS:
        return MarketOverviewResponse(market=market, available=False)
    key = f"macro:overview:{market}:{lang}"
    if (hit := await cache.get_model(redis, key, MarketOverviewResponse)) is not None:
        return hit
    rows, sector_rows, raw_events = await asyncio.gather(
        asyncio.to_thread(regime_view.load_state_rows, 30),
        asyncio.to_thread(regime_view.load_sector_rows),
        _calendar(redis),
    )
    strongest, weakest = regime_view.strongest_weakest(sector_rows, lang)
    resp = MarketOverviewResponse(
        market=market,
        available=True,
        macro_state=regime_view.build_state(rows, lang),
        next_event=next_key_event(filter_events(raw_events, market, datetime.now(UTC), lang)),
        strongest=strongest,
        weakest=weakest,
        sectors_as_of=sector_rows[0].trade_date if sector_rows else None,
    )
    if resp.macro_state is not None:
        await cache.set_model(redis, key, resp)
    return resp


async def get_sector_board(redis: Redis | None, market: str, lang: str = "zh",
                           parent: str | None = None, date: str | None = None) -> SectorBoardResponse:
    """行业弹层（parent 为一级行业 key 时返回其子行业）。

    date 给定时按该日收盘取强弱（雷达翻到哪天、筛选条就按哪天排序），不附带雷达买卖点数（App 用自己当天的统计）；
    不给时取最新一天并附带宽基雷达最新一天的买卖点数（旧版 App）。
    """
    if market not in MACRO_MARKETS:
        return SectorBoardResponse(market=market, available=False)
    key = f"macro:sectors:{market}:{parent or 'root'}:{lang}" + (f":{date}" if date else "")
    if (hit := await cache.get_model(redis, key, SectorBoardResponse)) is not None:
        return hit
    from app.services.signal_radar.sectors import BROAD_UNIVERSE
    from app.services.signal_radar.service import latest_sector_counts
    from app.services.signal_radar.universe import get_universe

    universe_key = BROAD_UNIVERSE[market]
    rows = await asyncio.to_thread(regime_view.load_sector_rows, parent, date)
    radar = (await latest_sector_counts(redis, market, universe_key)
             if redis is not None and parent is None and date is None else None)
    radar_date, counts = radar if radar else (None, {})
    universe = get_universe(market, universe_key)
    resp = SectorBoardResponse(
        market=market,
        available=True,
        as_of=rows[0].trade_date if rows else None,
        radar_universe=universe_key,
        radar_universe_name=universe.etf_name if universe else None,
        radar_date=radar_date,
        sectors=regime_view.sector_rows(rows, counts, lang),
        children_of=parent,
    )
    if rows:
        await cache.set_model(redis, key, resp)
    return resp
