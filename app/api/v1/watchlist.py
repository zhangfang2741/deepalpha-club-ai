"""自选股路由：登录用户的关注清单，加入/删除/查看。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.auth.dependencies import get_current_user
from app.core.logging import logger
from app.db.session import get_db
from app.models.user import User
from app.schemas.watchlist import WatchlistAddRequest, WatchlistItemOut, WatchlistResponse
from app.services import watchlist as store

router = APIRouter()


@router.get("", response_model=WatchlistResponse)
async def list_watchlist(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WatchlistResponse:
    """获取当前用户的自选列表，最近加入的在前。"""
    items = await store.list_items(db, user.id)
    return WatchlistResponse(
        items=[
            WatchlistItemOut(market=i.market, symbol=i.symbol, name=i.name, created_at=i.created_at)
            for i in items
        ]
    )


@router.post("", response_model=WatchlistItemOut)
async def add_to_watchlist(
    body: WatchlistAddRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WatchlistItemOut:
    """加入自选（已存在则幂等更新名称）。"""
    item = await store.add_item(db, user.id, body.market, body.symbol, body.name)
    logger.info("watchlist_item_added", user_id=user.id, market=item.market, symbol=item.symbol)
    return WatchlistItemOut(market=item.market, symbol=item.symbol, name=item.name, created_at=item.created_at)


@router.delete("/{market}/{symbol}")
async def remove_from_watchlist(
    market: str,
    symbol: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """移出自选。"""
    removed = await store.remove_item(db, user.id, market, symbol)
    if not removed:
        raise HTTPException(status_code=404, detail="自选里没有这只标的")
    logger.info("watchlist_item_removed", user_id=user.id, market=market, symbol=symbol)
    return {"removed": True}
