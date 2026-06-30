"""缠论分析 API"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.logging import logger
from app.schemas.chan import (
    ChanAnalysisResponse,
    FractalOut,
    MACDOut,
    MergedCandleOut,
    PivotOut,
    SegmentOut,
    SignalOut,
    StrokeOut,
)
from app.services.chan.analyzer import ChanAnalyzer
from app.services.skills.kline import fetch_kline

router = APIRouter()
_analyzer = ChanAnalyzer()


@router.get("/analysis", response_model=ChanAnalysisResponse)
async def chan_analysis(
    symbol: str = Query(description="股票代码，如 AAPL"),
    start_date: str = Query(description="开始日期，格式 YYYY-MM-DD"),
    end_date: str = Query(description="结束日期，格式 YYYY-MM-DD"),
    freq: str = Query(default="daily", description="K线周期：daily / weekly"),
) -> ChanAnalysisResponse:
    """对指定股票进行完整缠论分析。

    返回：合并K线、分型、笔、线段、中枢、背驰、买卖点、MACD。
    """
    logger.info("chan_analysis_request", symbol=symbol, start=start_date, end=end_date)

    bars = await fetch_kline(
        user_id=None,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        freq=freq,
    )

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
            FractalOut(type=f.type, time=f.time, price=f.price, idx=f.idx)
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
            )
            for seg in result.segments
        ],
        stroke_pivots=[
            PivotOut(
                zg=p.zg, zd=p.zd, gg=p.gg, dd=p.dd,
                start_time=p.start_time, end_time=p.end_time, level=p.level,
            )
            for p in result.stroke_pivots
        ],
        segment_pivots=[
            PivotOut(
                zg=p.zg, zd=p.zd, gg=p.gg, dd=p.dd,
                start_time=p.start_time, end_time=p.end_time, level=p.level,
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
            )
            for sig in result.signals
        ],
        current_trend=result.current_trend,
        summary=result.summary,
    )
