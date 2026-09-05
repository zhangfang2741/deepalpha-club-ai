"""八字排盘与 AI 解读 API 端点。"""

from fastapi import APIRouter, HTTPException, Request

from app.core.limiter import limiter
from app.core.logging import logger
from app.schemas.bazi import (
    BaziChartRequest,
    BaziChartResponse,
    InterpretationRequest,
    InterpretationResponse,
)
from app.services.bazi.chart import build_bazi_chart
from app.services.bazi.interpretation import generate_interpretation

router = APIRouter()


@router.post("/chart", response_model=BaziChartResponse)
@limiter.limit("20 per minute")
async def get_bazi_chart(request: Request, body: BaziChartRequest) -> BaziChartResponse:
    """根据生辰信息计算八字排盘（四柱/五行/十神/大运/流年）。"""
    logger.info("bazi_chart_requested", hour_known=body.birth_time is not None)
    return build_bazi_chart(body)


@router.post("/interpretation", response_model=InterpretationResponse)
@limiter.limit("10 per minute")
async def get_bazi_interpretation(request: Request, body: InterpretationRequest) -> InterpretationResponse:
    """调用 AI 生成今日运势(daily)或深度解读(deep)文案。"""
    logger.info("bazi_interpretation_requested", section=body.section)
    try:
        return await generate_interpretation(body)
    except Exception as e:
        logger.exception("bazi_interpretation_failed", section=body.section, error=str(e))
        raise HTTPException(status_code=502, detail="AI 解读生成失败，请稍后再试")
