"""行业恐慌指数 API 端点。"""

import datetime
from concurrent.futures import ALL_COMPLETED, ThreadPoolExecutor, wait
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from redis.asyncio import Redis

from app.cache.client import get_redis_optional
from app.core.logging import logger
from app.services.industry_panic.calculator import SECTOR_ETF_MAP, compute_sector_panic

router = APIRouter()

CACHE_KEY = "industry_panic:v1"
CACHE_TTL = 3600  # 1 小时


# ── Schemas ───────────────────────────────────────────────────────────────────

class PanicPoint(BaseModel):
    date: str
    rsi: float
    panic: float


class SectorPanic(BaseModel):
    sector_cn: str
    sector: str
    symbol: str
    current_rsi: Optional[float]
    current_panic: Optional[float]
    history: list[PanicPoint]


class IndustryPanicResponse(BaseModel):
    as_of: str
    sectors: list[SectorPanic]


# ── 端点 ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=IndustryPanicResponse)
async def get_industry_panic(
    redis: Optional[Redis] = Depends(get_redis_optional),
) -> IndustryPanicResponse:
    """获取 11 个 GICS 一级行业的历史 RSI 恐慌指数。

    panic = 100 - RSI(14)，基于行业代表性 SPDR ETF 日收盘价计算。
    结果缓存 1 小时；Redis 不可用时跳过缓存直接计算。
    """
    if redis is not None:
        try:
            cached = await redis.get(CACHE_KEY)
            if cached:
                logger.info("industry_panic_cache_hit")
                return IndustryPanicResponse.model_validate_json(cached)
        except Exception as e:
            logger.warning("industry_panic_cache_read_failed", error=str(e))
            # Redis 故障时降级到实时拉取，不中断请求

    logger.info("industry_panic_cache_miss")

    sectors: list[SectorPanic] = []

    with ThreadPoolExecutor(max_workers=11) as executor:
        futures = {
            executor.submit(compute_sector_panic, m["symbol"]): m
            for m in SECTOR_ETF_MAP
        }
        # 总超时 25s：11 个并发请求 × 8s httpx timeout，留出计算余量
        done, not_done = wait(futures, timeout=25, return_when=ALL_COMPLETED)
        for future in not_done:
            future.cancel()
        for future in done | not_done:
            meta = futures[future]
            try:
                history = future.result() if not future.cancelled() else []
            except Exception as e:
                logger.exception("industry_panic_sector_failed", symbol=meta["symbol"], error=str(e))
                history = []

            if history:
                last = history[-1]
                current_rsi = last["rsi"]
                current_panic = last["panic"]
            else:
                current_rsi = None
                current_panic = None

            sectors.append(
                SectorPanic(
                    sector_cn=meta["sector_cn"],
                    sector=meta["sector"],
                    symbol=meta["symbol"],
                    current_rsi=current_rsi,
                    current_panic=current_panic,
                    history=[PanicPoint(**p) for p in history],
                )
            )

    # 按中文名排序保持稳定顺序
    order = {m["symbol"]: i for i, m in enumerate(SECTOR_ETF_MAP)}
    sectors.sort(key=lambda s: order.get(s.symbol, 99))

    result = IndustryPanicResponse(
        as_of=datetime.date.today().isoformat(),
        sectors=sectors,
    )

    if redis is not None:
        try:
            await redis.set(CACHE_KEY, result.model_dump_json(), ex=CACHE_TTL)
            logger.info("industry_panic_cache_set", sector_count=len(sectors))
        except Exception as e:
            logger.warning("industry_panic_cache_write_failed", error=str(e))
    return result
