"""缠论分析 API"""
from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from redis.asyncio import Redis

from app.api.v1.auth import get_current_user
from app.cache.client import current_redis, get_redis
from app.cache.operations import get_gap_job, set_gap_job
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.user import User
from app.schemas.chan import (
    ChanAnalysisResponse,
    FractalOut,
    GapItemOut,
    GapJobStatus,
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

# 保持对后台任务的强引用，避免被 GC 提前回收
_background_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


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


async def _run_gap_job(job_id: str, user_id: int, body: StructureGapRequest) -> None:
    """后台执行 GAP 分析（拉K线 + 缠论 + LLM），把结果/错误写回 Redis。"""
    redis = current_redis()
    if redis is None:
        logger.error("chan_gap_job_no_redis", job_id=job_id)
        return

    async def _store(status: str, *, result: dict | None = None, error: str | None = None) -> None:
        await set_gap_job(
            redis, user_id, job_id,
            {"status": status, "user_id": user_id, "result": result, "error": error},
        )

    try:
        try:
            bars = await fetch_kline(
                user_id=user_id,
                symbol=body.symbol,
                start_date=body.start_date,
                end_date=body.end_date,
                freq=body.freq,
                redis=redis,
            )
        except ValueError as e:
            await _store("failed", error=str(e))
            return

        if not bars:
            await _store("failed", error=f"未获取到 {body.symbol} 的K线数据，请检查股票代码或日期范围")
            return

        result = _analyzer.analyze(body.symbol, bars)
        analysis = await analyze_structure_gap(result, body.industry_view)

        resp = StructureGapResponse(
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
        await _store("done", result=resp.model_dump())
        logger.info("chan_gap_job_done", job_id=job_id, symbol=body.symbol, gaps=len(analysis.gaps))
    except Exception as e:
        logger.exception("chan_gap_job_failed", job_id=job_id, symbol=body.symbol, error=str(e))
        await _store("failed", error="生成结构 gap 分析失败，请稍后再试")


@router.post("/gap", response_model=GapJobStatus)
@limiter.limit("10 per minute")
async def chan_structure_gap_submit(
    request: Request,
    body: StructureGapRequest,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> GapJobStatus:
    """提交一个【市场结构 × 产业结构】GAP 分析异步任务，立即返回 job_id。

    分析含 LLM 调用、耗时较长，改为异步：此处仅创建任务并后台执行，
    前端凭 job_id 轮询 GET /gap/{job_id} 取回结果。不预测涨跌、不构成投资建议。
    """
    if not body.industry_view or not body.industry_view.strip():
        raise HTTPException(status_code=400, detail="请先提供对该标的的产业结构判断")

    job_id = uuid4().hex
    await set_gap_job(
        redis, user.id, job_id,
        {"status": "pending", "user_id": user.id, "result": None, "error": None},
    )
    _spawn(_run_gap_job(job_id, user.id, body))

    logger.info("chan_gap_submitted", user_id=user.id, symbol=body.symbol, job_id=job_id)
    return GapJobStatus(job_id=job_id, status="pending")


@router.get("/gap/{job_id}", response_model=GapJobStatus)
async def chan_structure_gap_status(
    request: Request,
    job_id: str,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> GapJobStatus:
    """轮询 GAP 异步任务状态；done 时携带结果，failed 时携带错误信息。"""
    data = await get_gap_job(redis, user.id, job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期，请重新提交")

    result = None
    if data.get("result"):
        result = StructureGapResponse(**data["result"])

    return GapJobStatus(
        job_id=job_id,
        status=data.get("status", "pending"),
        result=result,
        error=data.get("error"),
    )
