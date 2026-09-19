"""自选股存取：直接对 watchlist_item 表做增删查，业务逻辑很薄不单独分层。"""
from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.watchlist import WatchlistItem


async def list_items(db: AsyncSession, user_id: int) -> list[WatchlistItem]:
    """按加入时间倒序，最近加入的在前。"""
    result = await db.execute(
        select(WatchlistItem)
        .where(WatchlistItem.user_id == user_id)
        .order_by(WatchlistItem.created_at.desc())
    )
    return list(result.scalars().all())


async def add_item(db: AsyncSession, user_id: int, market: str, symbol: str, name: str) -> WatchlistItem:
    """加入自选：已存在同 (market, symbol) 则视为幂等成功，只更新展示名称。"""
    symbol = symbol.strip().upper()
    existing = (
        await db.execute(
            select(WatchlistItem).where(
                WatchlistItem.user_id == user_id,
                WatchlistItem.market == market,
                WatchlistItem.symbol == symbol,
            )
        )
    ).scalars().first()
    if existing:
        existing.name = name
        db.add(existing)
        await db.commit()
        await db.refresh(existing)
        return existing

    item = WatchlistItem(user_id=user_id, market=market, symbol=symbol, name=name)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def remove_item(db: AsyncSession, user_id: int, market: str, symbol: str) -> bool:
    """移出自选。返回是否真的删到了一条（供 API 层决定是否 404）。"""
    symbol = symbol.strip().upper()
    existing = (
        await db.execute(
            select(WatchlistItem).where(
                WatchlistItem.user_id == user_id,
                WatchlistItem.market == market,
                WatchlistItem.symbol == symbol,
            )
        )
    ).scalars().first()
    if existing is None:
        return False
    await db.delete(existing)
    await db.commit()
    return True
