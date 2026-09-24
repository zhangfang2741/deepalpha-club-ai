"""信号雷达 API。

扫描各市场科技 ETF 成分股跑缠论，返回最近若干交易日「每日买卖点前 N 只」。
首次扫描较重（数十只 × 缠论），采用 stale-while-revalidate + generating 轮询：
- 命中且新鲜 → 直接返回 ready；
- 命中但陈旧（预热迟到/停摆）→ 先返回旧数据（ready），同时后台刷新，不让用户看空屏；
- 未命中（真正冷启动）→ 后台启动扫描并立即返回 status=generating，前端稍后重试。
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
from app.schemas.signal_radar import RadarUniverseOut, SignalRadarResponse
from app.services.signal_radar.service import DEFAULT_TOP_N, compute_market, peek_cache_entry
from app.services.signal_radar.universe import get_universe, list_universes, supported_markets

router = APIRouter()

_GENERATING_TTL = 300  # 后台扫描去重标记的存活时间（秒）
_background_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _generating_key(market: str, universe_key: str) -> str:
    return f"signal_radar:generating:{market}:{universe_key}"


async def _run_scan(market: str, universe_key: str, user_id: int) -> None:
    """后台执行一次全量扫描，完成后清除 generating 标记。"""
    redis = current_redis()
    if redis is None:
        logger.error("signal_radar_scan_no_redis", market=market)
        return
    try:
        await compute_market(market, redis=redis, user_id=user_id, universe_key=universe_key)
    except Exception as e:  # noqa: BLE001
        logger.exception("signal_radar_scan_failed", market=market, error=str(e))
    finally:
        try:
            await redis.delete(_generating_key(market, universe_key))
        except Exception:  # noqa: BLE001
            pass


@router.get("", response_model=SignalRadarResponse)
@limiter.limit("30 per minute")
async def signal_radar(
    request: Request,
    market: str = Query(default="us", description="市场：us / cn / hk"),
    universe: str | None = Query(
        default=None, description="universe 键，如 nasdaq100 / sp500；缺省=该市场默认（科技指数）"
    ),
    refresh: bool = Query(default=False, description="强制重新扫描（后台）"),
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> SignalRadarResponse:
    """获取某 (市场, universe) 最近交易日的缠论买卖点雷达。"""
    uni = get_universe(market, universe)
    if uni is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"不支持的市场/universe：{market}/{universe}，"
                f"市场可选 {', '.join(supported_markets())}"
            ),
        )

    cached, is_stale = await peek_cache_entry(redis, market, uni.key)

    # 需要触发一次后台扫描的情形：强制刷新、无任何缓存、或缓存已陈旧（预热迟到/停摆）。
    if refresh or cached is None or is_stale:
        # 去重：已有后台扫描在跑就不再重复启动（按 (市场, universe) 各自去重）；
        # 但用户主动 refresh 时无视去重，确保确实重扫一次。
        gkey = _generating_key(market, uni.key)
        already = await redis.get(gkey)
        if refresh or not already:
            await redis.set(gkey, "1", ex=_GENERATING_TTL)
            _spawn(_run_scan(market, uni.key, user.id))
            reason = "refresh" if refresh else ("cold" if cached is None else "stale")
            logger.info(
                "signal_radar_scan_spawned",
                market=market, universe=uni.key, user_id=user.id, reason=reason,
            )

    # 有缓存就先返回（stale-while-revalidate）：哪怕正在后台刷新，也不让用户看空屏。
    # 只有真正冷启动（连一份旧缓存都没有）才回 generating，让前端轮询等待首扫。
    if cached is not None:
        # 旧缓存可能仍有 15 只，响应时同步收窄，避免等待下一轮扫描才能生效。
        cached.top_n = DEFAULT_TOP_N
        for day in cached.days:
            day.signals = day.signals[:DEFAULT_TOP_N]
            day.buy_count = sum(signal.side == "buy" for signal in day.signals)
            day.sell_count = sum(signal.side == "sell" for signal in day.signals)
        return cached

    return SignalRadarResponse(
        market=market,
        universe=uni.key,
        universes=[
            RadarUniverseOut(key=u.key, name=u.etf_name, is_default=u.is_default)
            for u in list_universes(market)
        ],
        etf_name=uni.etf_name,
        universe_size=len(uni.constituents),
        as_of="",
        top_n=DEFAULT_TOP_N,
        days=[],
        status="generating",
    )
