"""量化研究接口：个股五维度量化研究 + 方法说明。业务逻辑见 app/services/quant_research。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Path, Query, Request
from redis.asyncio import Redis

from app.api.v1.auth import get_current_user
from app.cache.client import get_redis_optional
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.user import User
from app.schemas.quant_research import MethodologyOut, QuantResearchOut
from app.services.quant_research.methodology import build_methodology
from app.services.quant_research.service import get_quant_research

router = APIRouter()


@router.get("/methodology", response_model=MethodologyOut)
async def quant_methodology(lang: Literal["zh", "en"] = Query("zh")) -> MethodologyOut:
    """方法说明（「等级是怎么算的？」）。"""
    return build_methodology(lang)


@router.get("/{market}/{symbol}", response_model=QuantResearchOut)
@limiter.limit("20 per minute")
async def quant_research(
    request: Request,
    market: str = Path(..., pattern=r"^[a-zA-Z]{2}$"),
    symbol: str = Path(..., pattern=r"^[A-Za-z0-9][A-Za-z0-9\-\.]{0,11}$"),
    lang: Literal["zh", "en"] = Query("zh"),
    user: User = Depends(get_current_user),
    redis: Redis | None = Depends(get_redis_optional),
) -> QuantResearchOut:
    """个股量化研究（五维度、三层下钻所需的全部数据）。"""
    out = await get_quant_research(market, symbol, lang, redis=redis)
    logger.info("quant_research_served", market=market, symbol=symbol.upper(), status=out.status, user_id=user.id)
    return out
