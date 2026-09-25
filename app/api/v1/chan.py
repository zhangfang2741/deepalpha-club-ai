"""缠论分析 API"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
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
    MarketNarrativeOut,
    MergedCandleOut,
    PhaseBranchOut,
    PhaseChecklistItemOut,
    PivotOut,
    PivotPhaseOut,
    RecommendationOut,
    SegmentOut,
    StageGuideOut,
    StageGuideStepOut,
    StrokeOut,
    StructureGapRequest,
    StructureGapResponse,
    StructureLayerOut,
    SubLevelResponse,
)
from app.services.chan.analyzer import ChanAnalyzer
from app.services.chan.gap import analyze_structure_gap
from app.services.chan.sub_level_service import current_sub_level
from app.services.chan.sub_level_service import signal_out as _signal_out
from app.services.skills.kline import fetch_kline

router = APIRouter()
_analyzer = ChanAnalyzer()

# 窗口锚定的 warmup 天数：足够覆盖缠论左边界依赖的收敛区（实测 ~30 根合并K线）
_WARMUP_DAYS = {"daily": 180, "weekly": 540, "30min": 20}
# 30 分钟可见区间上限：港股/A 股的 Yahoo 分钟线最多约 60 天，美股 FMP 分钟线要分段请求；
# 可见 30 天 + 预热 20 天 ≈ 50 天，既在上限内，请求量也可控。
_MAX_VISIBLE_DAYS = {"30min": 30}


def _visible_start(start_date: str, end_date: str, freq: str) -> str:
    """可见区间起点：30 分钟级别收窄到最近 _MAX_VISIBLE_DAYS 天，日线/周线原样返回。"""
    cap = _MAX_VISIBLE_DAYS.get(freq)
    if cap is None:
        return start_date
    try:
        earliest = (date.fromisoformat(end_date[:10]) - timedelta(days=cap)).isoformat()
    except ValueError:
        return start_date
    return max(start_date, earliest)


def _anchor_start(start_date: str, freq: str, warmup_days: int | None = None) -> str:
    """把用户所选起点向前推 warmup 天，作为实际取数起点。

    warmup_days 参数已废弃、被忽略：详情页始终按周期默认预热（日线 180 / 周线 540）。
    czsc 要积累若干笔（一买 >=5、三买 >=7、二买 >=15）才开始出信号，不预热会让图表
    开头一两个月没有任何买卖点。旧版 iOS 从信号雷达点进来会传 0（为与雷达同区间），
    现在改由雷达把取数起点同步前移（见 signal_radar.service._fetch_start），两边
    区间仍完全一致。解析失败（非法日期）时原样返回 start_date。
    """
    days = _WARMUP_DAYS.get(freq, 180)
    try:
        d = date.fromisoformat(start_date[:10])
    except ValueError:
        return start_date
    return (d - timedelta(days=days)).isoformat()


def _zip_divergences(strokes: list, divergences: list) -> list[tuple]:
    """笔与笔级背驰按下标平行；笔数不足 3 的早退分支不计算背驰（列表为空），此时补 None。"""
    return [(s, divergences[i] if i < len(divergences) else None) for i, s in enumerate(strokes)]


async def _fetch_bars_or_http_error(
    user_id: int, symbol: str, start: str, end: str, freq: str, redis: Redis | None,
    *, use_cache: bool = True,
) -> list[dict]:
    """取 K 线；数据源错误转成可读的 HTTP 错误（400 可读原因 / 502 上游故障 / 404 无数据）。"""
    try:
        bars = await fetch_kline(
            user_id=user_id, symbol=symbol, start_date=start, end_date=end, freq=freq, redis=redis,
            use_cache=use_cache,
        )
    except ValueError as e:
        # 数据源配置错误、认证失败、限流等可读信息直接透传给用户
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("chan_kline_failed", symbol=symbol, error=str(e))
        raise HTTPException(status_code=502, detail=f"获取 {symbol} 行情数据失败，请稍后再试")
    if not bars:
        raise HTTPException(status_code=404, detail=f"未获取到 {symbol} 的K线数据，请检查股票代码或日期范围")
    return bars


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
    freq: str = Query(default="daily", pattern="^(daily|weekly|30min)$",
                      description="K线周期：daily / weekly / 30min（30 分钟可见区间最多近 30 天）"),
    lang: str = Query(default="zh", description="分析文案语言：zh / en"),
    warmup_days: int | None = Query(
        default=None, ge=0,
        description="已废弃、被忽略：详情页始终按默认预热（日线180/周线540），保留仅为兼容旧版 App",
    ),
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> ChanAnalysisResponse:
    """对指定股票进行完整缠论分析。

    返回：合并K线、分型、笔、线段、中枢、背驰、买卖点、MACD。
    """
    logger.info("chan_analysis_request", user_id=user.id, symbol=symbol, start=start_date, end=end_date)

    # 窗口锚定：在用户所选起点之前多取一段 warmup K 线一起送入缠论，在完整序列上
    # 计算以消除左边界依赖（结构不随用户选的起始日期漂移），再裁剪回可见窗口。
    # 实测 ~30 根合并K线即可让可见区结构收敛，这里给足冗余：日线 180 天、周线 540 天。
    start_date = _visible_start(start_date, end_date, freq)
    anchor_start = _anchor_start(start_date, freq, warmup_days)

    # 详情页现拉现算、不读K线缓存：盘中要看到刚走出的K线（单次取数约 1 秒，计算毫秒级）
    bars = await _fetch_bars_or_http_error(user.id, symbol, anchor_start, end_date, freq, redis,
                                           use_cache=False)
    result = _analyzer.analyze(symbol, bars, lang=lang, visible_from=start_date, freq=freq)

    pivot_phase_out: PivotPhaseOut | None = None
    if result.pivot_phase:
        # build_pivot_phase 的每条返回非 None PivotPhase 的路径都会设置 stage_guide，
        # 因此这里必然非 None；断言仅用于向 pyright 收窄类型，不是防御性兜底。
        assert result.pivot_phase.stage_guide is not None
        pivot_phase_out = PivotPhaseOut(
            phase=result.pivot_phase.phase,
            phase_label=result.pivot_phase.phase_label,
            direction=result.pivot_phase.direction,
            pivot=PivotOut(
                zg=result.pivot_phase.pivot.zg, zd=result.pivot_phase.pivot.zd,
                gg=result.pivot_phase.pivot.gg, dd=result.pivot_phase.pivot.dd,
                start_time=result.pivot_phase.pivot.start_time,
                end_time=result.pivot_phase.pivot.end_time,
                level=result.pivot_phase.pivot.level,
                confirmed=result.pivot_phase.pivot.confirmed,
            ),
            checklist=[
                PhaseChecklistItemOut(label=c.label, detail=c.detail, state=c.state)
                for c in result.pivot_phase.checklist
            ],
            reason=result.pivot_phase.reason,
            confirmed=result.pivot_phase.confirmed,
            branches=[
                PhaseBranchOut(outcome=b.outcome, condition_label=b.condition_label, result_label=b.result_label)
                for b in result.pivot_phase.branches
            ],
            stage_guide=StageGuideOut(
                current_index=result.pivot_phase.stage_guide.current_index,
                steps=[
                    StageGuideStepOut(key=s.key, title=s.title, detail=s.detail)
                    for s in result.pivot_phase.stage_guide.steps
                ],
                why_it_matters=result.pivot_phase.stage_guide.why_it_matters,
            ),
        )

    structure_layers_out = [
        StructureLayerOut(layer=layer.layer, label=layer.label, title=layer.title, detail=layer.detail)
        for layer in result.structure_layers
    ]

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
                volume=mc.volume,
                end_time=mc.end_time or None,
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
                power_price=s.power_price,
                power_volume=s.power_volume,
                length=s.length,
                diverged=dv.is_diverged if dv else False,
                # 未做比较（无前一个同向笔 / 未创新高低）的默认结果说明为空，不给比值
                price_ratio=dv.price_ratio if dv and dv.description else None,
            )
            for s, dv in _zip_divergences(result.strokes, result.divergences)
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
        signals=[_signal_out(sig) for sig in result.signals],
        current_trend=result.current_trend,
        walk_type=result.walk_type,
        walk_type_label=result.walk_type_label,
        trend_outlook=result.trend_outlook,
        trend_outlook_label=result.trend_outlook_label,
        summary=result.summary,
        narrative=MarketNarrativeOut(
            phase=result.narrative.phase,
            phase_label=result.narrative.phase_label,
            headline=result.narrative.headline,
            details=result.narrative.details,
        ) if result.narrative else None,
        pending_notes=result.pending_notes,
        recommendation=RecommendationOut(
            action=result.recommendation.action,
            action_label=result.recommendation.action_label,
            bias=result.recommendation.bias,
            reasons=result.recommendation.reasons,
            caveats=result.recommendation.caveats,
        ) if result.recommendation else None,
        pivot_phase=pivot_phase_out,
        structure_layers=structure_layers_out,
        structure_headline=result.structure_headline,
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

        result = _analyzer.analyze(body.symbol, bars, freq=body.freq)
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


@router.get("/sub-level", response_model=SubLevelResponse)
@limiter.limit("20 per minute")
async def chan_sub_level(
    request: Request,
    symbol: str = Query(description="股票代码，如 AAPL / 0700.HK / 600519.SS"),
    start_date: str = Query(description="日线可见起点，与分析详情页一致，格式 YYYY-MM-DD"),
    end_date: str = Query(description="结束日期，格式 YYYY-MM-DD"),
    lang: str = Query(default="zh", description="文案语言：zh / en"),
    parent_freq: str = Query(default="daily", pattern="^(daily|weekly)$",
                             description="大级别：daily（配 30 分钟）/ weekly（配日线）"),
    warmup_days: int | None = Query(default=None, ge=0, description="已废弃、被忽略，保留仅为兼容旧版 App"),
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> SubLevelResponse:
    """次级别确认：大级别定方向（与详情页同一窗口的形态倾向）× 次级别近期买卖点。

    日线配 30 分钟近两个交易日、周线配日线近两周。次级别取数失败或不足时
    verdict=unavailable，仍返回 200；大级别取数失败按 /analysis 同样报错。
    daily_bias* 字段名沿用（旧版 App 兼容），周线配对时即周线倾向。
    """
    logger.info("chan_sub_level_request", user_id=user.id, symbol=symbol, end=end_date,
                parent_freq=parent_freq)

    async def fetch_parent(start: str, end: str, freq: str) -> list[dict]:
        return await _fetch_bars_or_http_error(user.id, symbol, start, end, freq, redis, use_cache=False)

    # 与信号雷达共用唯一入口（固定口径 + 结论缓存）：气泡上的共振与这里是同一次计算。
    # start_date 不再参与次级别计算（结论描述「现在」，与详情页日期范围无关），保留兼容。
    # 详情页现拉现算（不读结论与K线缓存），新结论写回缓存，雷达下次读到的就是这份
    return await current_sub_level(symbol, parent_freq, end_date=end_date, user_id=user.id,
                                   redis=redis, lang=lang, fetch_parent=fetch_parent, use_cache=False)


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
