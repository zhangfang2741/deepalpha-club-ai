"""威科夫方法论分析 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from redis.asyncio import Redis

from app.api.v1.auth import get_current_user
from app.cache.client import get_redis
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.user import User
from app.schemas.wyckoff import (
    CandleOut,
    LawOut,
    PhaseOut,
    RecommendationOut,
    TradingRangeOut,
    WyckoffAnalysisResponse,
    WyckoffEventOut,
)
from app.services.skills.kline import fetch_kline
from app.services.wyckoff.analyzer import WyckoffAnalyzer

router = APIRouter()
_analyzer = WyckoffAnalyzer()


@router.get("/analysis", response_model=WyckoffAnalysisResponse)
@limiter.limit("20 per minute")
async def wyckoff_analysis(
    request: Request,
    symbol: str = Query(description="股票代码，如 AAPL"),
    start_date: str = Query(description="开始日期，格式 YYYY-MM-DD"),
    end_date: str = Query(description="结束日期，格式 YYYY-MM-DD"),
    freq: str = Query(default="daily", description="K线周期：daily / weekly"),
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> WyckoffAnalysisResponse:
    """对指定股票进行威科夫方法论分析。

    返回：K线、交易区间、威科夫事件、市场阶段、三大定律与操作建议。
    """
    logger.info("wyckoff_analysis_request", user_id=user.id, symbol=symbol, start=start_date, end=end_date)

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
        logger.exception("wyckoff_kline_failed", symbol=symbol, error=str(e))
        raise HTTPException(status_code=502, detail=f"获取 {symbol} 行情数据失败，请稍后再试")

    if not bars:
        raise HTTPException(status_code=404, detail=f"未获取到 {symbol} 的K线数据，请检查股票代码或日期范围")

    result = _analyzer.analyze(symbol, bars)

    return WyckoffAnalysisResponse(
        symbol=result.symbol,
        bars_count=result.bars_count,
        context=result.context,
        candles=[
            CandleOut(
                time=b["time"], open=float(b["open"]), high=float(b["high"]),
                low=float(b["low"]), close=float(b["close"]),
                volume=float(b.get("volume", 0) or 0),
            )
            for b in bars
        ],
        trading_range=TradingRangeOut(
            kind=result.trading_range.kind,
            support=result.trading_range.support,
            resistance=result.trading_range.resistance,
            start_time=result.trading_range.start_time,
            end_time=result.trading_range.end_time,
        ) if result.trading_range else None,
        events=[
            WyckoffEventOut(
                code=e.code, name=e.name, time=e.time, price=e.price,
                volume_ratio=e.volume_ratio, phase=e.phase, description=e.description,
            )
            for e in result.events
        ],
        phase=PhaseOut(
            stage=result.phase.stage,
            stage_label=result.phase.stage_label,
            phase=result.phase.phase,
            phase_label=result.phase.phase_label,
            breakout=result.phase.breakout,
        ) if result.phase else None,
        laws=[
            LawOut(key=law.key, name=law.name, verdict=law.verdict, detail=law.detail)
            for law in result.laws
        ],
        stage_label=result.stage_label,
        position_desc=result.position_desc,
        summary=result.summary,
        recommendation=RecommendationOut(
            action=result.recommendation.action,
            action_label=result.recommendation.action_label,
            bias=result.recommendation.bias,
            reasons=result.recommendation.reasons,
            caveats=result.recommendation.caveats,
        ) if result.recommendation else None,
    )
