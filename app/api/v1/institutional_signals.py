"""机构资金信号 API 端点。"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from redis.asyncio import Redis

from app.cache.client import get_redis_optional
from app.core.logging import logger
from app.schemas.institutional_signals import (
    InstitutionalSignalReport,
    LeaderboardResponse,
)
from app.services.institutional_signals import compute_institutional_signals
from app.services.institutional_signals.scan import scan_leaderboard

router = APIRouter()

CACHE_PREFIX = "institutional_signals"
CACHE_TTL = 3600  # 1 小时
LEADERBOARD_CACHE_KEY = "institutional_signals:leaderboard:v1"
LEADERBOARD_TTL = 21600  # 6 小时


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    redis: Optional[Redis] = Depends(get_redis_optional),
) -> LeaderboardResponse:
    """机构建仓榜：扫描 universe，按综合分与偏多状态排名。

    基于 4 个 FMP 维度（不含期权仓位），点进详情页查看完整五维。结果缓存 6 小时。
    """
    if redis is not None:
        try:
            cached = await redis.get(LEADERBOARD_CACHE_KEY)
            if cached:
                logger.info("institutional_signals_leaderboard_cache_hit")
                return LeaderboardResponse.model_validate_json(cached)
        except Exception as e:
            logger.warning("institutional_signals_leaderboard_cache_read_failed", error=str(e))

    logger.info("institutional_signals_leaderboard_cache_miss")
    result = await scan_leaderboard()

    if redis is not None:
        try:
            await redis.set(LEADERBOARD_CACHE_KEY, result.model_dump_json(), ex=LEADERBOARD_TTL)
        except Exception as e:
            logger.warning("institutional_signals_leaderboard_cache_write_failed", error=str(e))

    return result


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
