"""Fear & Greed Index API endpoints."""

from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.cache.client import get_redis
from app.core.logging import logger
from app.schemas.fear_greed import FearGreedResponse
from app.services.fear_greed import fear_greed_service

router = APIRouter()


@router.get("", response_model=FearGreedResponse)
async def get_fear_greed(redis: Redis = Depends(get_redis)) -> FearGreedResponse:
    """Get Fear & Greed Index history for the past 1 year with statistics snapshot."""
    logger.info("fear_greed_request")
    return await fear_greed_service.get_history(redis)
