"""自选股存取：直接对 watchlist_item 表做增删查，业务逻辑很薄不单独分层。"""
from __future__ import annotations

from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.watchlist import WatchlistItem
from app.services.signal_radar.universe import resolve_name

# 单用户自选上限。定死在这里而非 config.py：这是产品规则，不是环境相关配置。
MAX_ITEMS = 1


class WatchlistLimitExceeded(Exception):
    """加入自选时已达 MAX_ITEMS 上限，供 API 层转换成 400 响应。"""


def display_name(market: str, symbol: str, stored: str) -> str:
    """自选条目的展示名：存的名字为空或就等于代码时补上中文名，否则原样保留。

    补名字复用信号雷达同一套 curated 成分清单（如 2015 → 理想汽车），补不到就回落
    代码本身。读列表和加入时都过一遍，既修好历史上「只存了代码」的老条目，也保证
    以后新增的条目直接带上名称。
    """
    name = (stored or "").strip()
    if name and name.upper() != symbol.strip().upper():
        return name
    return resolve_name(market, symbol) or name or symbol


async def list_items(db: AsyncSession, user_id: int) -> list[WatchlistItem]:
    """按加入时间倒序，最近加入的在前。"""
    result = await db.execute(
        select(WatchlistItem)
        .where(WatchlistItem.user_id == user_id)
        .order_by(WatchlistItem.created_at.desc())
    )
    return list(result.scalars().all())


async def add_item(db: AsyncSession, user_id: int, market: str, symbol: str, name: str) -> WatchlistItem:
    """加入自选：已存在同 (market, symbol) 则视为幂等成功，只更新展示名称。

    未存在且已达 MAX_ITEMS 上限则抛 WatchlistLimitExceeded（幂等更新不受限，
    避免「已在自选里」的标的因为达到上限反而改不了名称）。
    """
    symbol = symbol.strip().upper()
    # 客户端只有代码没有真名时（name 传成了代码），用 curated 成分清单补中文名再落库，
    # 让存进去的就是「理想汽车」而不是「2015」。
    name = display_name(market, symbol, name)
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

    count = (
        await db.execute(
            select(func.count()).select_from(WatchlistItem).where(WatchlistItem.user_id == user_id)
        )
    ).scalar_one()
    if count >= MAX_ITEMS:
        raise WatchlistLimitExceeded(MAX_ITEMS)

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
