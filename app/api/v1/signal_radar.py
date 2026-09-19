"""信号雷达 API。

扫描各市场科技 ETF 成分股跑缠论，返回最近若干交易日「每日买卖点前 N 只」。
首次扫描较重（数十只 × 缠论），采用 generating 轮询模式：
- 命中缓存 → 直接返回 ready；
- 未命中 → 后台启动扫描并立即返回 status=generating，前端稍后重试。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from redis.asyncio import Redis

from app.api.v1.auth import get_current_user
from app.cache.client import current_redis, get_redis
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.user import User
from app.schemas.signal_radar import SignalRadarResponse
from app.services.signal_radar.service import compute_market, peek_cache
from app.services.signal_radar.universe import get_universe, supported_markets

router = APIRouter()

_GENERATING_TTL = 300  # 后台扫描去重标记的存活时间（秒）
_background_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _generating_key(market: str) -> str:
    return f"signal_radar:generating:{market}"


async def _run_scan(market: str, user_id: int) -> None:
    """后台执行一次全量扫描，完成后清除 generating 标记。"""
    redis = current_redis()
    if redis is None:
        logger.error("signal_radar_scan_no_redis", market=market)
        return
    try:
        await compute_market(market, redis=redis, user_id=user_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("signal_radar_scan_failed", market=market, error=str(e))
    finally:
        try:
            await redis.delete(_generating_key(market))
        except Exception:  # noqa: BLE001
            pass


@router.get("", response_model=SignalRadarResponse)
@limiter.limit("30 per minute")
async def signal_radar(
    request: Request,
    market: str = Query(default="us", description="市场：us / cn / hk"),
    refresh: bool = Query(default=False, description="强制重新扫描（后台）"),
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> SignalRadarResponse:
    """获取某市场最近交易日的缠论买卖点雷达。"""
    universe = get_universe(market)
    if universe is None:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的市场：{market}，可选 {', '.join(supported_markets())}",
        )

    if not refresh:
        cached = await peek_cache(redis, market)
        if cached is not None:
            return cached

    # 去重：已有后台扫描在跑就不再重复启动
    gkey = _generating_key(market)
    already = await redis.get(gkey)
    if not already or refresh:
        await redis.set(gkey, "1", ex=_GENERATING_TTL)
        _spawn(_run_scan(market, user.id))
        logger.info("signal_radar_scan_spawned", market=market, user_id=user.id)

    return SignalRadarResponse(
        market=market,
        etf_name=universe.etf_name,
        universe_size=len(universe.constituents),
        as_of="",
        top_n=10,
        days=[],
        status="generating",
    )
