"""自选股路由：登录用户的关注清单，加入/删除/查看。"""
from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.auth.dependencies import get_current_user
from app.cache.client import get_redis
from app.core.logging import logger
from app.db.session import get_db
from app.models.user import User
from app.schemas.watchlist import (
    WatchlistAddRequest,
    WatchlistItemOut,
    WatchlistPhaseOut,
    WatchlistPhasesResponse,
    WatchlistResponse,
)
from app.services import watchlist as store
from app.services.watchlist_phases import fetch_phase_labels

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
            WatchlistItemOut(
                market=i.market,
                symbol=i.symbol,
                # 历史上只存了代码的老条目，读取时用 curated 成分清单补中文名（如 2015
                # → 理想汽车），不必等用户重新加入。
                name=store.display_name(i.market, i.symbol, i.name),
                created_at=i.created_at,
            )
            for i in items
        ]
    )


@router.get("/phases", response_model=WatchlistPhasesResponse)
async def get_watchlist_phases(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> WatchlistPhasesResponse:
    """批量算一遍当前用户自选列表里每只标的的中枢阶段（见 pivot_phase.py）。

    单独成一个端点、不塞进 GET /watchlist：算阶段要拉 K 线+跑缠论分析，比
    纯 DB 查询慢得多，前端列表页可以先渲染出代码/名称，阶段标签异步补上，
    不用为了等阶段把整个列表都卡住。
    """
    items = await store.list_items(db, user.id)
    results = await fetch_phase_labels(
        [(i.market, i.symbol) for i in items], user_id=user.id, redis=redis,
    )
    return WatchlistPhasesResponse(phases={
        f"{r.market}:{r.symbol}": WatchlistPhaseOut(
            symbol=r.symbol, market=r.market, phase=r.phase, phase_label=r.phase_label,
        )
        for r in results
    })


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
