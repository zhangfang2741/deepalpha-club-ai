"""SEC EDGAR filing API 端点。"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from redis.asyncio import Redis

from app.cache.client import get_redis_optional
from app.core.logging import logger
from app.schemas.sec_filings import CompanyFilingsResponse
from app.services.sec_filings import sec_filings_service

router = APIRouter()


@router.get("/filings", response_model=CompanyFilingsResponse)
async def get_company_filings(
    query: str = Query(
        ...,
        description="股票代码或 CIK，如 AAPL / 320193",
        min_length=1,
        max_length=20,
    ),
    redis: Optional[Redis] = Depends(get_redis_optional),
) -> CompanyFilingsResponse:
    """获取某公司在 SEC 提交的全部 filing，并按 7 大分类分组。

    Args:
        query: 股票代码（AAPL）或 CIK（320193）。
    """
    logger.info("sec_filings_request", query=query)

    result = await sec_filings_service.get_company_filings(query, redis)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"未找到「{query}」对应的公司或 SEC 数据，请确认股票代码/CIK 是否正确",
        )
    return CompanyFilingsResponse.model_validate(result)
