"""缠论分析 API"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from redis.asyncio import Redis

from app.api.v1.auth import get_current_user
from app.cache.client import get_redis
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.user import User
from app.schemas.chan import (
    ChanAnalysisResponse,
    FractalOut,
    GapItemOut,
    MACDOut,
    MergedCandleOut,
    PivotOut,
    RecommendationOut,
    SegmentOut,
    SignalOut,
    StrokeOut,
    StructureGapRequest,
    StructureGapResponse,
)
from app.services.chan.analyzer import ChanAnalyzer
from app.services.chan.gap import analyze_structure_gap
from app.services.skills.kline import fetch_kline

router = APIRouter()
_analyzer = ChanAnalyzer()


@router.get("/analysis", response_model=ChanAnalysisResponse)
@limiter.limit("20 per minute")
async def chan_analysis(
    request: Request,
    symbol: str = Query(description="股票代码，如 AAPL"),
    start_date: str = Query(description="开始日期，格式 YYYY-MM-DD"),
    end_date: str = Query(description="结束日期，格式 YYYY-MM-DD"),
    freq: str = Query(default="daily", description="K线周期：daily / weekly"),
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> ChanAnalysisResponse:
    """对指定股票进行完整缠论分析。

    返回：合并K线、分型、笔、线段、中枢、背驰、买卖点、MACD。
    """
    logger.info("chan_analysis_request", user_id=user.id, symbol=symbol, start=start_date, end=end_date)

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
        # 数据源配置错误、认证失败、限流等可读信息直接透传给用户
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("chan_kline_failed", symbol=symbol, error=str(e))
        raise HTTPException(status_code=502, detail=f"获取 {symbol} 行情数据失败，请稍后再试")

    if not bars:
        raise HTTPException(status_code=404, detail=f"未获取到 {symbol} 的K线数据，请检查股票代码或日期范围")

    result = _analyzer.analyze(symbol, bars)

    return ChanAnalysisResponse(
        symbol=result.symbol,
        bars_count=result.bars_count,
        merged_candles=[
            MergedCandleOut(
                idx=mc.idx,
                time=mc.time,
                high=mc.high,
                low=mc.low,
                open=mc.open,
                close=mc.close,
            )
            for mc in result.merged_candles
        ],
        fractals=[
            FractalOut(type=f.type, time=f.time, price=f.price, idx=f.idx, confirmed=f.confirmed)
            for f in result.fractals
        ],
        strokes=[
            StrokeOut(
                direction=s.direction,
                start_time=s.start_time,
                end_time=s.end_time,
                start_price=s.start_price,
                end_price=s.end_price,
                high=s.high,
                low=s.low,
                confirmed=s.confirmed,
            )
            for s in result.strokes
        ],
        segments=[
            SegmentOut(
                direction=seg.direction,
                start_time=seg.start_time,
                end_time=seg.end_time,
                start_price=seg.start_price,
                end_price=seg.end_price,
                high=seg.high,
                low=seg.low,
                stroke_count=seg.stroke_count,
                confirmed=seg.confirmed,
            )
            for seg in result.segments
        ],
        stroke_pivots=[
            PivotOut(
                zg=p.zg, zd=p.zd, gg=p.gg, dd=p.dd,
                start_time=p.start_time, end_time=p.end_time, level=p.level,
                confirmed=p.confirmed,
            )
            for p in result.stroke_pivots
        ],
        segment_pivots=[
            PivotOut(
                zg=p.zg, zd=p.zd, gg=p.gg, dd=p.dd,
                start_time=p.start_time, end_time=p.end_time, level=p.level,
                confirmed=p.confirmed,
            )
            for p in result.segment_pivots
        ],
        macd=MACDOut(
            times=result.macd.times,
            dif=result.macd.dif,
            dea=result.macd.dea,
            bar=result.macd.bar,
        ) if result.macd else None,
        signals=[
            SignalOut(
                type=sig.type,
                label=sig.label,
                time=sig.time,
                price=sig.price,
                strength=sig.strength,
                is_buy=sig.is_buy,
                description=sig.description,
                area_ratio=sig.divergence.area_ratio if sig.divergence else None,
                confirmed=sig.confirmed,
            )
            for sig in result.signals
        ],
        current_trend=result.current_trend,
        summary=result.summary,
        pending_notes=result.pending_notes,
        recommendation=RecommendationOut(
            action=result.recommendation.action,
            action_label=result.recommendation.action_label,
            bias=result.recommendation.bias,
            reasons=result.recommendation.reasons,
            caveats=result.recommendation.caveats,
        ) if result.recommendation else None,
    )


@router.post("/gap", response_model=StructureGapResponse)
@limiter.limit("10 per minute")
async def chan_structure_gap(
    request: Request,
    body: StructureGapRequest,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> StructureGapResponse:
    """找出【市场结构（缠论技术面）】与【产业结构（用户判断）】之间的背离。

    先用缠论解读当前市场结构，再与用户提供的产业观点并置，重点输出二者矛盾之处。
    不预测涨跌、不构成投资建议。
    """
    if not body.industry_view or not body.industry_view.strip():
        raise HTTPException(status_code=400, detail="请先提供对该标的的产业结构判断")

    logger.info("chan_gap_request", user_id=user.id, symbol=body.symbol)

    try:
        bars = await fetch_kline(
            user_id=user.id,
            symbol=body.symbol,
            start_date=body.start_date,
            end_date=body.end_date,
            freq=body.freq,
            redis=redis,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("chan_gap_kline_failed", symbol=body.symbol, error=str(e))
        raise HTTPException(status_code=502, detail=f"获取 {body.symbol} 行情数据失败，请稍后再试")

    if not bars:
        raise HTTPException(status_code=404, detail=f"未获取到 {body.symbol} 的K线数据，请检查股票代码或日期范围")

    result = _analyzer.analyze(body.symbol, bars)

    try:
        analysis = await analyze_structure_gap(result, body.industry_view)
    except Exception as e:
        logger.exception("chan_gap_llm_failed", symbol=body.symbol, error=str(e))
        raise HTTPException(status_code=502, detail="生成结构 gap 分析失败，请稍后再试")

    return StructureGapResponse(
        symbol=body.symbol,
        aligned=analysis.aligned,
        gaps=[
            GapItemOut(
                dimension=g.dimension,
                market_says=g.market_says,
                industry_says=g.industry_says,
                direction=g.direction,
                interpretation=g.interpretation,
            )
            for g in analysis.gaps
        ],
        key_question=analysis.key_question,
        caveats=analysis.caveats,
    )
