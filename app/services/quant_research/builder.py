"""一只股票的计算管线与响应组装（批量与按需共用）。

两段式：evaluate() 算指标 → 打分 → 维度分；综合分分布要等全体维度分算完才有，
所以 finalize_overall() 单独一步。build_payload() 把结果组装成 QuantResearchOut（zh / en）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.quant_research.glossary import input_hint
from app.services.quant_research import copy as tx
from app.services.quant_research.education import metric_interpretation
from app.services.quant_research.inputs import StockInputs, analyst_count
from app.services.quant_research.markets import profile
from app.services.quant_research.metrics import (
    DISPLAY_ONLY_DIMENSIONS,
    DIMENSIONS,
    METRICS,
    MetricValue,
    compute_metrics,
)
from app.services.quant_research.revisions import (
    EstimatePoint,
    compute_revisions,
    revision_status,
)
from app.services.quant_research.scoring import (
    DimensionScore,
    Distributions,
    OverallScore,
    ScoredMetric,
    composite,
    effective_weights,
    mark_extremes,
    overall,
    pick_key_fact,
    score_dimension,
    score_metric,
)
from app.services.quant_research.stage import StageInfo, stage_of, weights_for
from app.services.quant_research.universe import sector_name
from app.schemas.quant_research import (
    AsOf,
    CashFlows,
    Dimension,
    FormulaInput,
    KeyFact,
    MetricFormula,
    MetricGroup,
    MetricOut,
    Overall,
    PeerGroup,
    QuantResearchOut,
    Stage,
)

METHODOLOGY_VERSION = "q7"  # q7：综合分按公司阶段给维度加权（不再等权），低权重维度无一票否决权；# q3：EPS 修正过渡期用外部一致预期趋势；q4：阶段改为营收增速主轴；q5：新增护城河（只展示）；q6：护城河改为独立模块（宽 / 窄 / 无），移出维度
_REVISION_LOOKBACK = {"eps_fy1_30d": 30, "eps_fy1_90d": 90, "eps_fy2_90d": 90, "rev_fy1_90d": 90}


@dataclass
class Evaluation:
    inp: StockInputs
    metrics: dict[str, MetricValue]
    dims: list[DimensionScore]
    stage: StageInfo | None
    n_analysts: int
    overall: OverallScore | None = None
    estimates_date: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def weights(self) -> dict[str, float]:
        """综合分里各维度的名义权重：按营收增速与现金流连续插值（无阶段 = 等权）。"""
        return self.stage.weights if self.stage else weights_for(None)

    @property
    def composite(self) -> float | None:
        return composite(self.dims, self.weights)


def revision_metrics(inp: StockInputs, history: list[EstimatePoint]) -> dict[str, MetricValue]:
    """EPS 修正四项（批量算分布与单股评估共用，保证口径一致）。"""
    fy1, fy2 = inp.fy1, inp.fy2
    return compute_revisions(history, inp.as_of, fy1.get("date") if fy1 else None,
                             fy2.get("date") if fy2 else None, analyst_count(fy1), trend=inp.eps_trend,
                             fy1_eps=_num(fy1.get("epsAvg")) if fy1 else None,
                             fy2_eps=_num(fy2.get("epsAvg")) if fy2 else None)


def _num(v: object) -> float | None:
    try:
        return None if v is None else float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def evaluate(inp: StockInputs, history: list[EstimatePoint], dists: Distributions,
             prev_grades: dict | None = None) -> Evaluation:
    """算指标（含 EPS 修正）→ 板块内打分 → 维度分，prev_grades 用于防抖。"""
    prev = prev_grades or {}
    metrics = compute_metrics(inp)
    n = analyst_count(inp.fy1)
    metrics |= revision_metrics(inp, history)
    rev_state, rev_days = revision_status(history, inp.as_of)
    bridged = {k for k in _REVISION_LOOKBACK if metrics[k].meta.get("source") == "trend"}
    if bridged:  # 外部趋势已补上部分指标，不再整维「积累中」
        rev_state = "ok"

    stage = stage_of(inp, metrics["rev_yoy"].value, metrics["rev_cagr3"].value)
    val_weights = stage.valuation_weights if stage else None   # 估值倍数按阶段配权重（百分位仍和整个板块比）
    dims: list[DimensionScore] = []
    unsupported = profile(inp.market).unsupported
    for dim in DIMENSIONS:
        keys = [k for k, d in METRICS.items() if d.dimension == dim and k not in unsupported]
        scored = [score_metric(k, metrics[k], dists.get((inp.sector_key, k)), prev.get(f"m:{k}")) for k in keys]
        if dim == "revisions":
            if rev_state == "accumulating":
                dims.append(score_dimension(dim, scored, None, accumulating_days=rev_days))
                continue
            expected = sum(1 for k in keys if _REVISION_LOOKBACK[k] <= rev_days or k in bridged)
            dims.append(score_dimension(dim, scored, prev.get(f"d:{dim}"), expected=expected))
        else:
            dims.append(score_dimension(dim, scored, prev.get(f"d:{dim}"),
                                        metric_weights=val_weights if dim == "valuation" else None))
    mark_extremes(dims)
    for d in dims:
        d.key_fact = pick_key_fact(d)
    snap_dates = [p.snapshot_date for p in history]
    return Evaluation(inp, metrics, dims, stage, n,
                      estimates_date=max(snap_dates).isoformat() if snap_dates else None)


def finalize_overall(ev: Evaluation, overall_dist: list[float], prev_grades: dict | None = None) -> Evaluation:
    """用全体综合分分布定综合等级（含一票否决）。"""
    ev.overall = overall(ev.dims, overall_dist, ev.n_analysts, (prev_grades or {}).get("overall"), ev.weights)
    return ev


def grades_of(ev: Evaluation) -> dict[str, str]:
    """存库给次日防抖用：m:<指标>、d:<维度>、overall。"""
    out: dict[str, str] = {}
    for d in ev.dims:
        if d.grade:
            out[f"d:{d.key}"] = d.grade
        for s in d.metrics:
            if s.grade:
                out[f"m:{s.key}"] = s.grade
    if ev.overall and ev.overall.grade:
        out["overall"] = ev.overall.grade
    return out


# ---------- 组装 ----------

def _pct(v: float | None) -> float | None:
    return round(v * 100, 1) if v is not None else None


def _formula_inputs(sm: ScoredMetric, ev: Evaluation, lang: tx.Lang) -> list[FormulaInput]:
    out = []
    for name, v in sm.mv.inputs:
        note = None
        if name in ("price", "close_now"):
            note = ev.inp.price_date
        elif name.endswith("_ntm") or name.endswith("_fy1") or name.endswith("_fy2"):
            meta = sm.mv.meta or ev.metrics["pe_fwd"].meta
            n = meta.get("n_analysts") or ev.n_analysts
            note = tx._i(lang, f"{n} 位分析师均值", f"mean of {n} analysts")
            e1, e2 = meta.get("eps_fy1"), meta.get("eps_fy2")
            if name == "eps_ntm" and e1 is not None and e2 is not None:
                note += tx._i(lang, f" · 由本财年 {e1:.2f} 与下财年 {e2:.2f} 按剩余时间加权",
                              f" · time-weighted from FY1 {e1:.2f} and FY2 {e2:.2f}")
        elif name in ("est_new", "est_old") and sm.mv.meta.get("source") == "trend":
            note = tx._i(lang, "过渡期：自有每日记录满 90 天前，用公开的一致预期趋势计算",
                         "Bridge period: computed from public consensus trends until our daily records reach 90 days")
        elif name.endswith("_ttm") or name in ("equity", "assets", "invested", "nopat", "market_cap", "ev"):
            note = ev.inp.fiscal_period
        out.append(FormulaInput(label=tx.label(name, lang), value=tx.fmt_input(name, v, lang), note=note,
                                hint=input_hint(name, lang)))
    return out


def metric_weight(ev: Evaluation, key: str) -> float:
    """这一项在维度分里的实际权重：估值倍数按阶段（连续插值），其余取 MetricDef.weight。"""
    d = METRICS[key]
    if d.dimension == "valuation" and ev.stage is not None:
        return round(ev.stage.valuation_weights.get(key, d.weight), 3)
    return d.weight


def _metric_out(sm: ScoredMetric, ev: Evaluation, lang: tx.Lang) -> MetricOut:
    d = METRICS[sm.key]
    expr = tx.metric_expression(sm.key, sm.mv, lang)
    weight = metric_weight(ev, sm.key)
    status_note = tx.metric_status_note(sm, lang)
    if weight == 0 and ev.stage is not None:  # 本阶段不用这项倍数：仍展示，但写明不参与
        status_note = status_note or tx.stage_unused_note(tx.stage_name(ev.stage.key, lang), lang)
    return MetricOut(
        key=sm.key, name=d.name_zh if lang == "zh" else d.name_en,
        description=d.desc_zh if lang == "zh" else d.desc_en, direction=d.direction,
        value=sm.mv.value, display_value=tx.fmt_metric_display(sm.key, sm.mv.value, lang),
        status=sm.status, status_note=status_note,
        percentile=sm.percentile, grade=sm.grade,
        sector_median=sm.sector_median,
        sector_median_display=tx.fmt_metric_display(sm.key, sm.sector_median, lang) if sm.sector_median is not None else None,
        diff_to_median_pct=round(sm.diff_to_median_pct, 1) if sm.diff_to_median_pct is not None else None,
        distribution=sm.distribution,
        formula=MetricFormula(expression=expr, inputs=_formula_inputs(sm, ev, lang)) if expr else None,
        position_text=tx.position_text(sm, lang),
        interpretation=metric_interpretation(d, lang),
        weight=weight,
    )


def _dimension_out(d: DimensionScore, ev: Evaluation, lang: tx.Lang,
                   weights: dict[str, float] | None = None) -> Dimension:
    groups: dict[str, list[MetricOut]] = {}
    for sm in d.metrics:
        md = METRICS[sm.key]
        groups.setdefault(md.group if lang == "zh" else md.group_en, []).append(_metric_out(sm, ev, lang))
    fact = next((s for s in d.metrics if s.key == d.key_fact), None)
    return Dimension(
        key=d.key, name=tx.dimension_name(d.key, lang), description=tx.dimension_desc(d.key, lang),
        grade=d.grade, score=d.score, status=d.status,  # type: ignore[arg-type]
        status_note=tx.dimension_status_note(d, lang),
        is_highest=d.is_highest, is_lowest=d.is_lowest,
        key_fact=KeyFact(metric=fact.key, text=tx.key_fact_text(fact, lang)) if fact else None,
        formula=tx.dimension_formula(d, {k: metric_weight(ev, k) for k in (m.key for m in d.metrics)}),
        groups=[MetricGroup(name=k, metrics=v) for k, v in groups.items()],
        counts_in_overall=d.key not in DISPLAY_ONLY_DIMENSIONS,
        weight_pct=round(weights[d.key] * 100) if weights and d.key in weights else None,
    )


def build_payload(ev: Evaluation, lang: tx.Lang, *, in_universe: bool, sector_sample: int) -> QuantResearchOut:
    """把一只股票的评估结果组装成接口响应。"""
    inp, o = ev.inp, ev.overall
    sname = sector_name(inp.sector_key, lang)
    notes = [n for n in (tx.overall_note(o, lang) if o else None,
                         tx.dims_used_note(o.dimensions_used, lang) if o and o.grade else None) if n]
    eff_weights = effective_weights(ev.dims, ev.weights)
    stage = None
    if ev.stage:
        stage = Stage(key=ev.stage.key, name=tx.stage_name(ev.stage.key, lang), unprofitable=ev.stage.unprofitable,
                      cash_flows=CashFlows(operating=ev.stage.operating, investing=ev.stage.investing,
                                           financing=ev.stage.financing),
                      note=tx.stage_note(ev.stage.key, ev.stage.unprofitable, lang),
                      revenue_growth_pct=_pct(ev.stage.revenue_growth),
                      revenue_cagr_3y_pct=_pct(ev.stage.revenue_cagr_3y))
    return QuantResearchOut(
        market=inp.market, symbol=inp.symbol, name=inp.name, status="ok",
        methodology_version=METHODOLOGY_VERSION,
        as_of=AsOf(price_date=inp.price_date, fiscal_period=inp.fiscal_period, filing_date=inp.filing_date,
                   estimates_date=ev.estimates_date, currency_note=tx.currency_note(inp.fx, lang)),
        peer_group=PeerGroup(sector_key=inp.sector_key, sector_name=sname, sample_size=sector_sample,
                             in_universe=in_universe,
                             text=tx.peer_text(sname, sector_sample, lang, in_universe, inp.market),
                             universe_name=profile(inp.market).universe(lang)),
        stage=stage,
        overall=Overall(grade=o.grade if o else None, score=o.score if o else None,
                        universe_percentile=o.universe_percentile if o else None,
                        dimensions_used=o.dimensions_used if o else 0, capped=bool(o and o.capped),
                        note=("；" if lang == "zh" else "; ").join(notes) or None,
                        text=tx.overall_text(o, lang, inp.market) if o else None),
        dimensions=[_dimension_out(d, ev, lang, eff_weights) for d in ev.dims],
        disclaimer=tx.DISCLAIMER[lang],
    )


def unsupported(market: str, symbol: str, lang: tx.Lang) -> QuantResearchOut:
    """不支持的市场（二期再接港股 / A 股）。"""
    return QuantResearchOut(
        market=market, symbol=symbol, name=None, status="unsupported_market",
        status_note=tx._i(lang, "基本面研究暂只支持美股", "Fundamental research currently covers US stocks only"),
        methodology_version=METHODOLOGY_VERSION, disclaimer=tx.DISCLAIMER[lang],
    )


def insufficient(market: str, symbol: str, lang: tx.Lang, reason: str | None = None) -> QuantResearchOut:
    """数据不足（批量尚未跑过、样本外股票拉不到报表等）。"""
    return QuantResearchOut(
        market=market, symbol=symbol, name=None, status="insufficient_data",
        status_note=reason or tx._i(lang, "暂无足够数据生成基本面研究", "Not enough data for fundamental research yet"),
        methodology_version=METHODOLOGY_VERSION, disclaimer=tx.DISCLAIMER[lang],
    )


def sector_sample_sizes(dists: Distributions) -> dict[str, int]:
    """各板块样本数：取收盘价动量指标（几乎全覆盖）的分布长度。"""
    return {sector: len(v) for (sector, key), v in dists.items() if key == "r3m"}

