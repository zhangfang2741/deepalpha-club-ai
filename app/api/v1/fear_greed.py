"""Fear & Greed Index API endpoints."""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis

from app.cache.client import get_redis
from app.core.logging import logger
from app.schemas.fear_greed import FearGreedResponse
from app.services.fear_greed import fear_greed_service

router = APIRouter()


@router.get("", response_model=FearGreedResponse)
async def get_fear_greed(
    start_date: Optional[str] = Query(
        None,
        description="起始日期 YYYY-MM-DD，默认取一年前",
    ),
    end_date: Optional[str] = Query(
        None,
        description="结束日期 YYYY-MM-DD，默认取今天",
    ),
    redis: Redis = Depends(get_redis),
) -> FearGreedResponse:
    """Get Fear & Greed Index history with optional date range filter.

    Args:
        start_date: Filter history from this date (YYYY-MM-DD). Defaults to 1 year ago.
        end_date: Filter history to this date (YYYY-MM-DD). Defaults to today.
    """
    logger.info("fear_greed_request", start_date=start_date, end_date=end_date)

    # Parse dates if provided
    start = None
    end = None
    if start_date:
        start = date.fromisoformat(start_date)
    if end_date:
        end = date.fromisoformat(end_date)

    return await fear_greed_service.get_history(redis, start_date=start, end_date=end)
