"""信号雷达 API。

扫描各市场指数成分股跑缠论，返回最近若干交易日每天在场的全部买卖点（scope=all，新版 App，按出现时间排）；
不带 scope 的旧版 App 仍按旧综合分截取每天前 N（service.legacy_view）。
首次扫描较重（数十只 × 缠论），采用 stale-while-revalidate + generating 轮询：
- 命中且新鲜 → 直接返回 ready；
- 命中但陈旧（预热迟到/停摆）→ 先返回旧数据（ready），同时后台刷新，不让用户看空屏；
- 未命中（真正冷启动）→ 后台启动扫描并立即返回 status=generating，前端稍后重试。
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.auth import get_current_user
from app.cache.client import current_redis, get_redis
from app.cache.operations import acquire_lock, release_lock
from app.core.limiter import limiter
from app.core.logging import logger
from app.db.session import get_db
from app.models.user import User
from app.schemas.signal_radar import (
    RadarAnalystEventsResponse,
    RadarFundamentalResponse,
    RadarGradeEventsResponse,
    RadarSectorDayOut,
    RadarSectorPoolsOut,
    SignalRadarResponse,
)
from app.services.signal_radar.service import (
    DEFAULT_TOP_N,
    WATCHLIST_KEY,
    _universes_out,
    compute_demo_day,
    compute_market,
    peek_cache_entry,
    read_demo_cache,
    read_watchlist_cache,
    demo_lock_key,
    legacy_view,
    scan_lock_key,
    sector_day,
    sector_pools,
    SCAN_LOCK_TTL,
)
from app.services.chan.signal_policy import DEFAULT_MODE, normalize_mode
from app.services.watchlist import display_name, list_items
from app.services.signal_radar.analyst_events import analyst_events
from app.services.signal_radar.fundamental_top import fundamental_top
from app.services.signal_radar.quality_view import QUALITY_MODES, apply_quality
from app.services.signal_radar.grade_events import grade_events
from app.services.signal_radar.universe import get_universe, supported_markets

router = APIRouter()

_GENERATING_TTL = SCAN_LOCK_TTL  # 见 service.SCAN_LOCK_TTL
# 主动刷新的冷却：快照在这么多秒内刚算过就不再重扫——多人同时下拉刷新时，
# 只有第一次真正触发扫描，其余直接用这份新快照。
_REFRESH_COOLDOWN_SECONDS = 300


def _recently_computed(resp: SignalRadarResponse | None) -> bool:
    """快照是否在刷新冷却期内算出。"""
    if resp is None or not resp.computed_at:
        return False
    try:
        computed = datetime.fromisoformat(resp.computed_at)
    except ValueError:
        return False
    return (datetime.now(UTC) - computed).total_seconds() < _REFRESH_COOLDOWN_SECONDS
_background_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _generating_key(market: str, universe_key: str, mode: str = DEFAULT_MODE) -> str:
    return scan_lock_key(market, universe_key, mode)


_MODE_QUERY = Query(default=None, description="买卖点口径：loose（默认）/ strict，见 /chan/signal-modes")
_SCOPE_QUERY = Query(
    default="top", pattern="^(top|all)$",
    description="all = 每天在场的全部信号、按出现时间排（新版 App）；top = 旧版 App，按旧综合分截取前 N",
)


_QUALITY_QUERY = Query(
    default=None,
    description="good = 只留当前综合等级达标（A+ ~ B+）的股票的买卖点，并给气泡补分析师角标（新版 App，需 scope=all；"
                "不带则不筛选，旧版 App 行为不变）；good_xm = 同 good，但综合分与一票否决都不含动量维度",
)


async def _finish(resp: SignalRadarResponse, scope: str, quality: str | None, redis: Redis) -> SignalRadarResponse:
    """按 scope 截取 + 可选的基本面门槛（只对 scope=all 生效，旧版 App 的 top 视图不动）。"""
    out = _scoped(resp, scope)
    if quality in QUALITY_MODES and scope == "all":
        return await apply_quality(out, redis, mode=quality)
    return out


def _scoped(resp: SignalRadarResponse, scope: str) -> SignalRadarResponse:
    """按 scope 返回：all 原样（全部在场信号）；top 给旧版 App 截取前 N。"""
    return resp if scope == "all" else legacy_view(resp, DEFAULT_TOP_N)


async def _run_watchlist_scan(
    market: str, user_id: int, watchlist: list[tuple[str, str]], mode: str = DEFAULT_MODE,
) -> None:
    """后台扫描某用户的自选股，完成后清除该用户的 generating 标记。"""
    redis = current_redis()
    if redis is None:
        return
    try:
        await compute_market(market, redis=redis, user_id=user_id, watchlist=watchlist, mode=mode)
    except Exception as e:  # noqa: BLE001
        logger.exception("signal_radar_watchlist_scan_failed", market=market, error=str(e))
    finally:
        try:
            await release_lock(redis, _generating_key(market, f"{WATCHLIST_KEY}:u{user_id}", mode))
        except Exception:  # noqa: BLE001
            pass


async def _watchlist_radar(
    market: str, user: User, db: AsyncSession, redis: Redis, refresh: bool, mode: str = DEFAULT_MODE,
    scope: str = "top",
) -> SignalRadarResponse:
    """「自选」股票池：当前用户该市场的自选股；命中缓存直接返回，否则后台扫描并回 generating。"""
    items = [i for i in await list_items(db, user.id) if i.market == market]
    watchlist = [(i.symbol, display_name(market, i.symbol, i.name)) for i in items]

    def empty(status: str) -> SignalRadarResponse:
        return SignalRadarResponse(
            market=market, universe=WATCHLIST_KEY, universes=_universes_out(market), etf_name="自选",
            universe_size=len(watchlist), as_of="", top_n=DEFAULT_TOP_N, days=[], status=status,
            signal_mode=mode,
        )

    if not watchlist:
        return empty("ready")  # 自选里还没有该市场的股票，前端提示去加入
    cached = await read_watchlist_cache(redis, market, user.id, watchlist, mode)
    if cached and (not refresh or _recently_computed(cached)):
        return _scoped(cached, scope)
    # 原子抢锁：同一用户同一市场只跑一轮自选扫描（连点刷新、多端同时打开都不会叠加）
    gkey = _generating_key(market, f"{WATCHLIST_KEY}:u{user.id}", mode)
    if await acquire_lock(redis, gkey, _GENERATING_TTL):
        _spawn(_run_watchlist_scan(market, user.id, watchlist, mode))
        logger.info("signal_radar_watchlist_scan_spawned", market=market, user_id=user.id, size=len(watchlist))
    return empty("generating")


async def _run_scan(
    market: str, universe_key: str, user_id: int, refresh: bool = False, mode: str = DEFAULT_MODE,
) -> None:
    """后台执行一次全量扫描，完成后清除 generating 标记。refresh=True 时连成分股（含中文名）一起重建。"""
    redis = current_redis()
    if redis is None:
        logger.error("signal_radar_scan_no_redis", market=market)
        return
    try:
        await compute_market(market, redis=redis, user_id=user_id, universe_key=universe_key,
                             refresh_constituents=refresh, mode=mode)
    except Exception as e:  # noqa: BLE001
        logger.exception("signal_radar_scan_failed", market=market, error=str(e))
    finally:
        try:
            await release_lock(redis, _generating_key(market, universe_key, mode))
        except Exception:  # noqa: BLE001
            pass


def _demo_generating_key(market: str, universe_key: str, mode: str = DEFAULT_MODE) -> str:
    return demo_lock_key(market, universe_key, mode)


async def _run_demo_scan(market: str, universe_key: str, mode: str = DEFAULT_MODE) -> None:
    """后台算一次免费预览快照（「上个月 1 号」），完成后清除 generating 标记。"""
    redis = current_redis()
    if redis is None:
        logger.error("signal_radar_demo_scan_no_redis", market=market, universe=universe_key)
        return
    try:
        await compute_demo_day(market, universe_key, redis=redis, mode=mode)
    except Exception as e:  # noqa: BLE001
        logger.exception("signal_radar_demo_scan_failed", market=market, universe=universe_key, error=str(e))
    finally:
        try:
            await release_lock(redis, _demo_generating_key(market, universe_key, mode))
        except Exception:  # noqa: BLE001
            pass


@router.get("/sector-pools", response_model=RadarSectorPoolsOut)
@limiter.limit("60 per minute")
async def signal_radar_sector_pools(
    request: Request,
    market: str = Query(default="us", description="市场：us / cn / hk"),
    universe: str = Query(description="universe 键（当前雷达的指数，如 nasdaq100 / sp500）"),
    date: str = Query(description="交易日 YYYY-MM-DD", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    mode: str | None = _MODE_QUERY,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> RadarSectorPoolsOut:
    """某一天全部行业的气泡（App 行业筛选条一次取回，切行业不再请求）：只读行业池，不触发扫描。"""
    uni = get_universe(market, universe)
    if uni is None:
        raise HTTPException(status_code=400, detail=f"不支持的市场/universe：{market}/{universe}")
    return await sector_pools(redis, market, uni.key, date, normalize_mode(mode))


@router.get("/sector-day", response_model=RadarSectorDayOut)
@limiter.limit("60 per minute")
async def signal_radar_sector_day(
    request: Request,
    market: str = Query(default="us", description="市场：us / cn / hk"),
    universe: str = Query(description="universe 键（行业筛选用宽基，如 sp500）"),
    date: str = Query(description="交易日 YYYY-MM-DD", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    sector: str = Query(description="行业 key，如 technology"),
    mode: str | None = _MODE_QUERY,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> RadarSectorDayOut:
    """按行业筛选的某一天气泡：只读组装快照时存下的行业池，不触发扫描（不绕开扫描锁）。"""
    uni = get_universe(market, universe)
    if uni is None:
        raise HTTPException(status_code=400, detail=f"不支持的市场/universe：{market}/{universe}")
    return await sector_day(redis, market, uni.key, date, sector, normalize_mode(mode))


@router.get("/demo", response_model=SignalRadarResponse)
@limiter.limit("30 per minute")
async def signal_radar_demo(
    request: Request,
    market: str = Query(default="us", description="市场：us / cn / hk"),
    universe: str | None = Query(
        default=None, description="universe 键，如 nasdaq100 / sp500；缺省=该市场默认（科技指数）"
    ),
    mode: str | None = _MODE_QUERY,
    scope: str = _SCOPE_QUERY,
    quality: str | None = _QUALITY_QUERY,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> SignalRadarResponse:
    """免费预览：未订阅高级版的用户在信号雷达上唯一能点开的一天。

    「上个月 1 号」的真实快照（所选 universe，缺省为该市场默认），不是虚构数据，点进去
    能看到真实的分析详情。按 (市场, universe) 分别计算与缓存——同一市场切换指数时
    示例日要跟着换。跟主接口一样走 generating 轮询：命中缓存直接返回，未命中后台起算
    并回 generating。自选（watchlist）是高级版功能，不提供免费预览。
    """
    uni = get_universe(market, universe)
    if uni is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"不支持的市场/universe：{market}/{universe}，"
                f"市场可选 {', '.join(supported_markets())}"
            ),
        )
    mode = normalize_mode(mode)
    cached = await read_demo_cache(redis, market, uni.key, mode)
    if cached is not None:
        return await _finish(cached, scope, quality, redis)

    gkey = _demo_generating_key(market, uni.key, mode)
    if await acquire_lock(redis, gkey, _GENERATING_TTL):
        _spawn(_run_demo_scan(market, uni.key, mode))
        logger.info("signal_radar_demo_scan_spawned", market=market, universe=uni.key, user_id=user.id)

    return SignalRadarResponse(
        market=market,
        universe=uni.key,
        universes=_universes_out(market),
        etf_name=uni.etf_name,
        universe_size=len(uni.constituents),
        as_of="",
        top_n=DEFAULT_TOP_N,
        days=[],
        status="generating",
        signal_mode=mode,
    )


@router.get("/grade-events", response_model=RadarGradeEventsResponse)
@limiter.limit("30 per minute")
async def signal_radar_grade_events(
    request: Request,
    market: str = Query(default="us", description="市场：us / cn / hk"),
    universe: str | None = Query(default=None, description="universe 键；缺省=该市场默认"),
    days: int = Query(default=10, ge=1, le=30, description="最近多少个自然日"),
    user: User = Depends(get_current_user),  # noqa: ARG001
    redis: Redis = Depends(get_redis),
) -> RadarGradeEventsResponse:
    """基本面研究 tab：股票池里每天综合等级升 / 降的股票（事实陈列，不打分不推荐）。"""
    resp = await grade_events(market, universe, redis=redis, days=days)
    if resp is None:
        raise HTTPException(status_code=400, detail=f"不支持的市场/universe：{market}/{universe}")
    return resp


@router.get("/fundamental-top", response_model=RadarFundamentalResponse)
@limiter.limit("30 per minute")
async def signal_radar_fundamental_top(
    request: Request,
    market: str = Query(default="us", description="市场：us / cn / hk"),
    universe: str | None = Query(default=None, description="universe 键；缺省=该市场默认"),
    limit: int = Query(default=50, ge=1, le=100, description="返回前多少只（按综合等级从高到低）"),
    user: User = Depends(get_current_user),  # noqa: ARG001
    redis: Redis = Depends(get_redis),
) -> RadarFundamentalResponse:
    """基本面雷达：股票池里当前综合等级最高的若干只（含近 30 天券商评级净上调 / 下调角标，仅美股）。"""
    resp = await fundamental_top(market, universe, redis=redis, limit=limit)
    if resp is None:
        raise HTTPException(status_code=400, detail=f"不支持的市场/universe：{market}/{universe}")
    return resp


@router.get("/analyst-events", response_model=RadarAnalystEventsResponse)
@limiter.limit("30 per minute")
async def signal_radar_analyst_events(
    request: Request,
    market: str = Query(default="us", description="市场：us / cn / hk（仅美股有数据，其余 supported=false）"),
    universe: str | None = Query(default=None, description="universe 键；缺省=该市场默认"),
    days: int = Query(default=10, ge=1, le=30, description="最近多少个自然日"),
    user: User = Depends(get_current_user),  # noqa: ARG001
    redis: Redis = Depends(get_redis),
) -> RadarAnalystEventsResponse:
    """分析师评级 tab：股票池里每天被券商净上调 / 净下调评级的股票（事实陈列，不打分不推荐）。"""
    resp = await analyst_events(market, universe, redis=redis, days=days)
    if resp is None:
        raise HTTPException(status_code=400, detail=f"不支持的市场/universe：{market}/{universe}")
    return resp


@router.get("", response_model=SignalRadarResponse)
@limiter.limit("30 per minute")
async def signal_radar(
    request: Request,
    market: str = Query(default="us", description="市场：us / cn / hk"),
    universe: str | None = Query(
        default=None, description="universe 键，如 nasdaq100 / sp500；缺省=该市场默认（科技指数）"
    ),
    refresh: bool = Query(default=False, description="强制重新扫描（后台）"),
    mode: str | None = _MODE_QUERY,
    scope: str = _SCOPE_QUERY,
    quality: str | None = _QUALITY_QUERY,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
) -> SignalRadarResponse:
    """获取某 (市场, universe) 最近交易日的缠论买卖点雷达；universe=watchlist 为用户自选。"""
    mode = normalize_mode(mode)
    if universe == WATCHLIST_KEY and market in supported_markets():
        return await _watchlist_radar(market, user, db, redis, refresh, mode, scope)
    uni = get_universe(market, universe)
    if uni is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"不支持的市场/universe：{market}/{universe}，"
                f"市场可选 {', '.join(supported_markets())}"
            ),
        )

    cached, is_stale = await peek_cache_entry(redis, market, uni.key, mode)

    # 主动刷新在冷却期内（刚算过）视同普通请求，避免多人同时下拉刷新接连重扫
    if refresh and _recently_computed(cached):
        refresh = False
    # 需要触发一次后台扫描的情形：强制刷新、无任何缓存、或缓存已陈旧（预热迟到/停摆）。
    if refresh or cached is None or is_stale:
        # 去重：原子抢锁（SET NX），同一 (口径, 市场, universe) 任一时刻只有一轮扫描——
        # 多人同时请求、刷新、定时预热撞在一起都只跑一次；正在扫描时刷新也不再叠加，
        # 等这一轮结果即可。
        gkey = _generating_key(market, uni.key, mode)
        if await acquire_lock(redis, gkey, _GENERATING_TTL):
            _spawn(_run_scan(market, uni.key, user.id, refresh=refresh, mode=mode))
            reason = "refresh" if refresh else ("cold" if cached is None else "stale")
            logger.info(
                "signal_radar_scan_spawned",
                market=market, universe=uni.key, user_id=user.id, reason=reason, mode=mode,
            )

    # 有缓存就先返回（stale-while-revalidate）：哪怕正在后台刷新，也不让用户看空屏。
    # 只有真正冷启动（连一份旧缓存都没有）才回 generating，让前端轮询等待首扫。
    if cached is not None:
        return await _finish(cached, scope, quality, redis)

    return SignalRadarResponse(
        market=market,
        universe=uni.key,
        universes=_universes_out(market),
        etf_name=uni.etf_name,
        universe_size=len(uni.constituents),
        as_of="",
        top_n=DEFAULT_TOP_N,
        days=[],
        status="generating",
        signal_mode=mode,
    )
