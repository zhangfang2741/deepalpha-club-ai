"""一目均衡表分析 API"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from redis.asyncio import Redis

from app.api.v1.auth import get_current_user
from app.cache.client import get_redis
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.user import User
from app.schemas.ichimoku import (
    CandleOut,
    IchimokuAnalysisResponse,
    IchimokuSignalOut,
    IchimokuStateOut,
    LinePointOut,
    RecommendationOut,
)
from app.services.ichimoku.analyzer import IchimokuAnalyzer
from app.services.skills.kline import fetch_kline

router = APIRouter()
_analyzer = IchimokuAnalyzer()


def _points(points) -> list[LinePointOut]:
    return [LinePointOut(time=p.time, value=p.value) for p in points]


@router.get("/analysis", response_model=IchimokuAnalysisResponse)
@limiter.limit("20 per minute")
async def ichimoku_analysis(
    request: Request,
    symbol: str = Query(description="股票代码，如 AAPL"),
    start_date: str = Query(description="开始日期，格式 YYYY-MM-DD"),
    end_date: str = Query(description="结束日期，格式 YYYY-MM-DD"),
    freq: str = Query(default="daily", description="K线周期：daily / weekly"),
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> IchimokuAnalysisResponse:
    """对指定股票进行完整一目均衡表分析。

    返回：K线、转换线、基准线、先行带 A/B（云）、迟行线、买卖信号、当前状态与操作建议。
    """
    logger.info("ichimoku_analysis_request", user_id=user.id, symbol=symbol, start=start_date, end=end_date)

    try:
        bars = await fetch_kline(
            user_id=user.id,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            freq=freq,
            redis=redis,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("ichimoku_kline_failed", symbol=symbol, error=str(e))
        raise HTTPException(status_code=502, detail=f"获取 {symbol} 行情数据失败，请稍后再试")

    if not bars:
        raise HTTPException(status_code=404, detail=f"未获取到 {symbol} 的K线数据，请检查股票代码或日期范围")

    result = _analyzer.analyze(symbol, bars)

    return IchimokuAnalysisResponse(
        symbol=result.symbol,
        bars_count=result.bars_count,
        conversion_period=_analyzer.conversion_period,
        base_period=_analyzer.base_period,
        span_b_period=_analyzer.span_b_period,
        displacement=_analyzer.displacement,
        candles=[
            CandleOut(time=c.time, open=c.open, high=c.high, low=c.low, close=c.close)
            for c in result.candles
        ],
        tenkan=_points(result.tenkan),
        kijun=_points(result.kijun),
        senkou_a=_points(result.senkou_a),
        senkou_b=_points(result.senkou_b),
        chikou=_points(result.chikou),
        signals=[
            IchimokuSignalOut(
                type=s.type,
                label=s.label,
                time=s.time,
                price=s.price,
                strength=s.strength,
                is_buy=s.is_buy,
                description=s.description,
            )
            for s in result.signals
        ],
        state=IchimokuStateOut(
            price=result.state.price,
            price_vs_cloud=result.state.price_vs_cloud,
            cloud_color=result.state.cloud_color,
            tk_relation=result.state.tk_relation,
            chikou_relation=result.state.chikou_relation,
            tenkan=result.state.tenkan,
            kijun=result.state.kijun,
            cloud_top=result.state.cloud_top,
            cloud_bottom=result.state.cloud_bottom,
        ) if result.state else None,
        summary=result.summary,
        recommendation=RecommendationOut(
            action=result.recommendation.action,
            action_label=result.recommendation.action_label,
            bias=result.recommendation.bias,
            reasons=result.recommendation.reasons,
            caveats=result.recommendation.caveats,
        ) if result.recommendation else None,
    )
