"""八字排盘与 AI 解读 API 端点。"""

from fastapi import APIRouter

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
async def get_bazi_chart(request: BaziChartRequest) -> BaziChartResponse:
    """根据生辰信息计算八字排盘（四柱/五行/十神/大运/流年）。"""
    return build_bazi_chart(request)


@router.post("/interpretation", response_model=InterpretationResponse)
async def get_bazi_interpretation(request: InterpretationRequest) -> InterpretationResponse:
    """调用 AI 生成今日运势(daily)或深度解读(deep)文案。"""
    return await generate_interpretation(request)
