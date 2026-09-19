"""三地恐慌指数 API：美股 VIX(CNN Fear&Greed) / A股上证指数 RSI / 港股恒生指数 RSI，统一折算成 0~100 分。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from redis.asyncio import Redis

from app.cache.client import get_redis
from app.core.logging import logger
from app.schemas.panic_index import PanicIndexResponse
from app.services.panic_index import get_panic_index

router = APIRouter()

_SUPPORTED_MARKETS = {"us", "cn", "hk"}


@router.get("", response_model=PanicIndexResponse)
async def panic_index(
    market: str = Query(default="us", description="市场：us / cn / hk"),
    redis: Redis = Depends(get_redis),
) -> PanicIndexResponse:
    """获取某市场的恐慌指数（当前值 + 近一周/一月快照 + 历史曲线）。"""
    if market not in _SUPPORTED_MARKETS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的市场：{market}，可选 {', '.join(sorted(_SUPPORTED_MARKETS))}",
        )

    logger.info("panic_index_request", market=market)
    return await get_panic_index(redis, market)
