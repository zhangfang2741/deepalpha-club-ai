"""A 股平台数据 API：K 线 / 实时快照 / 基本面。

数据源：K 线走东方财富直连（前复权），快照/基本面走 akshare。
K 线做 DB 缓存（price_bars），减少对外请求。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.session import get_db
from app.models.price_bar import PriceBar
from app.schemas.astock import (
    FundamentalResponse,
    KlineBar,
    KlineResponse,
    QuoteResponse,
)
from app.services.astock.client import (
    AStockDataUnavailable,
    fetch_daily_bars,
    fetch_fundamental,
    fetch_quote,
)
from app.services.astock.symbols import InvalidSymbolError, normalize_symbol

router = APIRouter()


def _normalize_or_400(symbol: str) -> str:
    """归一化标的代码，非法则 400。"""
    try:
        return normalize_symbol(symbol)
    except InvalidSymbolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _load_cached_bars(
    db: AsyncSession, symbol: str, start: str, end: str
) -> list[dict]:
    """从 price_bars 读区间内已缓存的 K 线（升序）。"""
    stmt = (
        select(PriceBar)
        .where(PriceBar.symbol == symbol)
        .where(PriceBar.date >= start)
        .where(PriceBar.date <= end)
        .order_by(PriceBar.date)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "date": r.date,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume,
        }
        for r in rows
    ]


async def _upsert_bars(db: AsyncSession, symbol: str, bars: list[dict]) -> None:
    """批量写入/更新 K 线缓存（symbol+date 冲突则更新价格）。"""
    if not bars:
        return
    now = datetime.now(UTC)
    values = [
        {
            "symbol": symbol,
            "date": b["date"],
            "open": b["open"],
            "high": b["high"],
            "low": b["low"],
            "close": b["close"],
            "volume": b.get("volume", 0.0),
            "created_at": now,
            "updated_at": now,
        }
        for b in bars
    ]
    stmt = pg_insert(PriceBar).values(values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_price_bar_symbol_date",
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
            "updated_at": now,
        },
    )
    await db.execute(stmt)
    await db.commit()


@router.get("/kline", response_model=KlineResponse)
async def get_kline(
    symbol: str = Query(..., description="A 股代码，如 600519 / 600519.SH"),
    start: str | None = Query(None, description="起始日 YYYY-MM-DD，默认一年前"),
    end: str | None = Query(None, description="结束日 YYYY-MM-DD，默认今天"),
    db: AsyncSession = Depends(get_db),
) -> KlineResponse:
    """日 K 线（前复权）。命中缓存直接返回，否则拉取并回填缓存。"""
    norm = _normalize_or_400(symbol)
    today = datetime.now(UTC).date()
    end = end or today.strftime("%Y-%m-%d")
    start = start or (today - timedelta(days=365)).strftime("%Y-%m-%d")

    try:
        bars = await fetch_daily_bars(norm, start, end)
    except AStockDataUnavailable as exc:
        # 数据源不可用时退回缓存，尽量给结果
        cached = await _load_cached_bars(db, norm, start, end)
        if cached:
            logger.warning("astock_kline_served_from_cache", symbol=norm)
            return KlineResponse(symbol=norm, bars=[KlineBar(**b) for b in cached])
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    await _upsert_bars(db, norm, bars)
    return KlineResponse(symbol=norm, bars=[KlineBar(**b) for b in bars])


@router.get("/quote", response_model=QuoteResponse)
async def get_quote(
    symbol: str = Query(..., description="A 股代码"),
) -> QuoteResponse:
    """实时快照。"""
    norm = _normalize_or_400(symbol)
    try:
        data = await fetch_quote(norm)
    except AStockDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if data is None:
        raise HTTPException(status_code=404, detail=f"未找到标的：{norm}")
    return QuoteResponse(**data)


@router.get("/fundamental", response_model=FundamentalResponse)
async def get_fundamental(
    symbol: str = Query(..., description="A 股代码"),
) -> FundamentalResponse:
    """基本面/关键指标。"""
    norm = _normalize_or_400(symbol)
    try:
        data = await fetch_fundamental(norm)
    except AStockDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return FundamentalResponse(**data)
