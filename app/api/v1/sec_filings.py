"""SEC EDGAR filing API 端点。"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from redis.asyncio import Redis

from app.cache.client import get_redis_optional
from app.core.logging import logger
from app.schemas.sec_filings import (
    CompanyFilingsResponse,
    CompanyProfileResponse,
    FilingDocumentsResponse,
)
from app.services.sec_filings import company_profile_service, sec_filings_service
from app.services.sec_filings.company_profile import ProfileGenerationError

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


@router.get("/filing-documents", response_model=FilingDocumentsResponse)
async def get_filing_documents(
    cik: str = Query(..., description="公司 CIK（10 位或去零均可）", min_length=1, max_length=20),
    accession: str = Query(..., description="accession number，如 0000320193-26-000011", min_length=5, max_length=30),
    redis: Optional[Redis] = Depends(get_redis_optional),
) -> FilingDocumentsResponse:
    """获取单份 filing 的文档/附件清单（8-K 会高亮业绩新闻稿 EX-99.x）。

    Args:
        cik: 公司 CIK。
        accession: filing 的 accession number。
    """
    logger.info("sec_filing_documents_request", cik=cik, accession=accession)

    result = await sec_filings_service.get_filing_documents(cik, accession, redis)
    if result is None:
        raise HTTPException(status_code=404, detail="未找到该 filing 的文档清单")
    return FilingDocumentsResponse.model_validate(result)


@router.get("/company-profile", response_model=CompanyProfileResponse)
async def get_company_profile(
    query: str = Query(
        ...,
        description="股票代码或 CIK，如 AAPL / 320193",
        min_length=1,
        max_length=20,
    ),
    name: str = Query("", description="前端已知的公司名（可选，避免二次回源 SEC）", max_length=200),
    sic: str = Query("", description="前端已知的 SIC 行业描述（可选）", max_length=200),
    redis: Optional[Redis] = Depends(get_redis_optional),
) -> CompanyProfileResponse:
    """用大模型生成公司基础画像：行业、供应链位置、主要产品、核心差异化竞争力、主要竞争对手。

    结果按 CIK 缓存 7 天。

    Args:
        query: 股票代码（AAPL）或 CIK（320193）。
        name: 前端已知公司名，作为提示传入以省去回源。
        sic: 前端已知行业描述。
    """
    logger.info("sec_company_profile_request", query=query)

    try:
        result = await company_profile_service.get_profile(
            query, redis, name_hint=name, sic_hint=sic
        )
    except ProfileGenerationError as e:
        # 大模型生成失败：与「公司未找到」区分，便于前端展示与排查
        raise HTTPException(
            status_code=502,
            detail="大模型生成公司画像失败，请稍后重试（可能是模型服务暂时不可用或限流）",
        ) from e

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"未找到「{query}」对应的公司，请确认股票代码/CIK 是否正确",
        )
    return CompanyProfileResponse.model_validate(result)
