"""Skill factor explorer API: SSE code generation, K-line pre-load, and Skill execution."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis

from app.api.v1.auth import get_current_user
from app.cache.client import get_redis
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.user import User
from app.schemas.skills import (
    KlineResponse,
    SkillGenerateRequest,
    SkillGenerateResponse,
    SkillRunRequest,
    SkillRunResponse,
)
from app.services.skills import (
    execute_skill,
    fetch_and_cache_kline,
    generate_skill_stream,
    get_cached_price_df,
)

router = APIRouter()


@router.post("/generate")
@limiter.limit("20 per minute")
async def generate_skill(
    request: Request,
    body: SkillGenerateRequest,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream Skill factor code generation via SSE.

    Each event has the format: data: {"content": "...", "done": false}
    """
    logger.info(
        "skill_generate_request",
        user_id=user.id,
        turns=len(body.messages),
    )

    async def event_generator():
        try:
            async for chunk in generate_skill_stream(body.messages):
                payload = SkillGenerateResponse(content=chunk, done=False)
                yield f"data: {payload.model_dump_json()}\n\n"
            yield f"data: {SkillGenerateResponse(content='', done=True).model_dump_json()}\n\n"
        except Exception as e:
            logger.exception("skill_generate_failed", user_id=user.id, error=str(e))
            yield f"data: {SkillGenerateResponse(content=str(e), done=True).model_dump_json()}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/kline", response_model=KlineResponse)
@limiter.limit("30 per minute")
async def get_kline(
    request: Request,
    symbol: str = Query(..., min_length=1, max_length=20),
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    freq: Literal["daily", "weekly"] = Query("daily"),
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> KlineResponse:
    """Pre-load K-line data and write to Redis cache for reuse during Skill execution."""
    logger.info("skill_kline_request", user_id=user.id, symbol=symbol)
    try:
        bars, _ = await fetch_and_cache_kline(redis, symbol, start_date, end_date, freq)
        return KlineResponse(symbol=symbol, freq=freq, klines=bars)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("skill_kline_failed", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=f"K 线数据获取失败：{e}")


@router.post("/run", response_model=SkillRunResponse)
@limiter.limit("10 per minute")
async def run_skill(
    request: Request,
    body: SkillRunRequest,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> SkillRunResponse:
    """Execute Skill code and return factor data, reusing cached price data from Redis."""
    logger.info("skill_run_request", user_id=user.id, symbol=body.symbol)
    try:
        price_df = await get_cached_price_df(redis, body.symbol, body.start_date, body.end_date, body.freq)
        if price_df is None:
            bars, price_df = await fetch_and_cache_kline(
                redis, body.symbol, body.start_date, body.end_date, body.freq
            )

        factor_points, output_type = await execute_skill(
            body.code, price_df, body.symbol, body.start_date, body.end_date
        )
        return SkillRunResponse(
            symbol=body.symbol,
            output_type=output_type,
            factor=factor_points,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("skill_run_failed", user_id=user.id, symbol=body.symbol, error=str(e))
        raise HTTPException(status_code=500, detail=f"Skill 执行失败：{e}")
