"""宏观环境 / 市场概览 API（雷达页顶部宏观格、行业格及其弹层）。公开行情数据，不需要登录。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from redis.asyncio import Redis

from app.cache.client import get_redis
from app.core.logging import logger
from app.schemas.macro import MacroResponse, MarketOverviewResponse, SectorBoardResponse
from app.services.macro.service import get_macro, get_overview, get_sector_board

router = APIRouter()

_MARKETS = {"us", "cn", "hk"}
_LANG_QUERY = Query(default="zh", pattern="^(zh|en)$")


def _check(market: str) -> None:
    if market not in _MARKETS:
        raise HTTPException(status_code=400, detail=f"不支持的市场：{market}")


@router.get("/{market}/overview", response_model=MarketOverviewResponse)
async def market_overview(market: str, lang: str = _LANG_QUERY,
                          redis: Redis = Depends(get_redis)) -> MarketOverviewResponse:
    """顶部宏观格 + 行业格摘要。"""
    _check(market)
    logger.info("macro_overview_request", market=market)
    return await get_overview(redis, market, lang)


@router.get("/{market}/sectors", response_model=SectorBoardResponse)
async def sector_board(market: str, lang: str = _LANG_QUERY,
                       parent: str | None = Query(default=None, description="下钻：一级行业 key"),
                       redis: Redis = Depends(get_redis)) -> SectorBoardResponse:
    """行业弹层：各行业相对强弱 + 状态 + 宽基雷达当日按行业的买卖点数。"""
    _check(market)
    return await get_sector_board(redis, market, lang, parent)


@router.get("/{market}", response_model=MacroResponse)
async def macro(market: str, lang: str = _LANG_QUERY, redis: Redis = Depends(get_redis)) -> MacroResponse:
    """宏观弹层：市场状态 + 近一年状态色带 + 驱动因素 + 未来 7 天宏观日历。"""
    _check(market)
    logger.info("macro_request", market=market)
    return await get_macro(redis, market, lang)
