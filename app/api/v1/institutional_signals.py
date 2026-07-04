"""机构资金信号 API 端点。"""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from redis.asyncio import Redis

from app.cache.client import current_redis, get_redis_optional
from app.core.logging import logger
from app.schemas.institutional_signals import (
    InstitutionalSignalReport,
    LeaderboardResponse,
)
from app.services.institutional_signals import compute_institutional_signals
from app.services.institutional_signals.constants import SCAN_FRESH_SECONDS
from app.services.institutional_signals.scan import scan_leaderboard

router = APIRouter()

CACHE_PREFIX = "institutional_signals"
CACHE_TTL = 3600  # 1 小时

# 榜单缓存：stale-while-revalidate
LB_DATA_KEY = "institutional_signals:leaderboard:v2"
LB_FRESH_KEY = "institutional_signals:leaderboard:fresh"
LB_LOCK_KEY = "institutional_signals:leaderboard:lock"
LB_DATA_TTL = 86400   # 数据保留 24h（过期前一直可作为 stale 返回）
LB_LOCK_TTL = 900     # 扫描锁 15min，防并发重复扫描

# 保持对后台任务的强引用，避免被 GC 回收
_background_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _refresh_leaderboard() -> None:
    """后台扫描 universe 并写缓存；用锁避免并发重复扫描。"""
    redis = current_redis()
    if redis is not None:
        try:
            got = await redis.set(LB_LOCK_KEY, b"1", nx=True, ex=LB_LOCK_TTL)
            if not got:
                return  # 已有扫描在进行
        except Exception as e:
            logger.warning("leaderboard_lock_failed", error=str(e))
    try:
        result = await scan_leaderboard()
        if redis is not None:
            await redis.set(LB_DATA_KEY, result.model_dump_json(), ex=LB_DATA_TTL)
            await redis.set(LB_FRESH_KEY, b"1", ex=SCAN_FRESH_SECONDS)
        logger.info("leaderboard_refreshed", scanned=result.scanned)
    except Exception:
        logger.exception("leaderboard_refresh_failed")
    finally:
        if redis is not None:
            try:
                await redis.delete(LB_LOCK_KEY)
            except Exception:
                pass


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    redis: Optional[Redis] = Depends(get_redis_optional),
) -> LeaderboardResponse:
    """机构建仓榜：扫描动态 universe（S&P 500 成分股），按综合分与偏多状态排名。

    基于 4 个 FMP 维度（不含期权仓位），点进详情页查看完整五维。
    stale-while-revalidate：命中缓存立即返回；过期则先返回旧数据再后台刷新；
    无缓存则后台开扫并返回 computing，前端稍后重试。
    """
    if redis is None:
        # 无缓存无法后台化，返回 computing 提示（详情页查询不受影响）
        return LeaderboardResponse(status="computing", note="缓存不可用，榜单暂不可用")

    try:
        cached = await redis.get(LB_DATA_KEY)
        fresh = await redis.exists(LB_FRESH_KEY)
    except Exception as e:
        logger.warning("leaderboard_cache_read_failed", error=str(e))
        cached, fresh = None, False

    if cached:
        if not fresh:
            _spawn(_refresh_leaderboard())  # 过期：后台刷新，本次先返回旧数据
        return LeaderboardResponse.model_validate_json(cached)

    _spawn(_refresh_leaderboard())
    return LeaderboardResponse(status="computing", note="正在后台扫描 universe，请稍后刷新")


@router.get("", response_model=InstitutionalSignalReport)
async def get_institutional_signals(
    symbol: str = Query(..., min_length=1, max_length=10, description="股票代码，如 AAPL"),
    redis: Optional[Redis] = Depends(get_redis_optional),
) -> InstitutionalSignalReport:
    """获取单支标的的机构资金信号报告（五维评分 + 状态标签）。

    维度：Expectation（预期）/ Positioning（仓位）/ Participation（参与度）/
    Fundamental（基本面）/ Confirmation（确认）。当前 Phase 1 覆盖预期与参与度。
    结果缓存 1 小时；Redis 不可用时降级实时计算。
    """
    symbol = symbol.upper().strip()
    if not symbol.isalpha():
        raise HTTPException(status_code=422, detail="股票代码仅允许字母")

    cache_key = f"{CACHE_PREFIX}:{symbol}:v1"

    if redis is not None:
        try:
            cached = await redis.get(cache_key)
            if cached:
                logger.info("institutional_signals_cache_hit", symbol=symbol)
                return InstitutionalSignalReport.model_validate_json(cached)
        except Exception as e:
            logger.warning("institutional_signals_cache_read_failed", symbol=symbol, error=str(e))

    logger.info("institutional_signals_cache_miss", symbol=symbol)
    report = await compute_institutional_signals(symbol)

    if redis is not None:
        try:
            await redis.set(cache_key, report.model_dump_json(), ex=CACHE_TTL)
        except Exception as e:
            logger.warning("institutional_signals_cache_write_failed", symbol=symbol, error=str(e))

    return report
