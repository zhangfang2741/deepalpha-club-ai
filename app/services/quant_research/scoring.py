"""打分聚合：板块分布 → 指标百分位 / 等级 → 维度分 → 综合分 + 一票否决。纯函数。

规则见设计 §3.2–3.5：not_meaningful 按最差（百分位 0）参与；not_applicable / missing /
样本不足不参与；维度分 = 参与指标百分位等权平均，参与数不足一半 → 维度不可用；
综合分 = 可用维度等权平均，在全体样本中的百分位定等级；任一维度 < 20（F）→ 综合最高 C+；
分析师不足 3 位不给综合等级。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.services.quant_research.grading import cap_grade, grade_with_hysteresis, percentile_of
from app.services.quant_research.metrics import DIMENSIONS, METRICS, MIN_ANALYSTS, MetricValue, Status

MIN_SAMPLE = 20
CAP_THRESHOLD = 20.0   # 维度分低于它（F）触发一票否决
CAP_CEILING = "C+"
OVERALL_SECTOR = "_all"
OVERALL_KEY = "_overall"


@dataclass
class ScoredMetric:
    key: str
    mv: MetricValue
    status: Status
    percentile: float | None          # None = 不参与
    grade: str | None
    sample_size: int
    sector_median: float | None = None
    diff_to_median_pct: float | None = None
    distribution: dict[str, float] | None = None


@dataclass
class DimensionScore:
    key: str
    status: str                       # ok | unavailable | accumulating
    score: float | None
    grade: str | None
    metrics: list[ScoredMetric]
    is_highest: bool = False
    is_lowest: bool = False
    key_fact: str | None = None       # 指标 key
    days_accumulated: int | None = None


@dataclass
class OverallScore:
    score: float | None
    universe_percentile: float | None
    grade: str | None
    dimensions_used: int
    capped: bool = False
    cap_dimension: str | None = None
    extra: dict = field(default_factory=dict)


Distributions = dict[tuple[str, str], list[float]]


def build_distributions(universe: dict[str, tuple[str, dict[str, MetricValue]]]) -> Distributions:
    """(板块, 指标) → 升序数值（只收 ok 的值）。"""
    buckets: dict[tuple[str, str], list[float]] = {}
    for sector, metrics in universe.values():
        for key, mv in metrics.items():
            if mv.status == "ok" and mv.value is not None and math.isfinite(mv.value):
                buckets.setdefault((sector, key), []).append(float(mv.value))
    return {k: sorted(v) for k, v in buckets.items()}


def quantile(sorted_values: list[float], q: float) -> float:
    """线性插值分位数。"""
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    pos = q * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def score_metric(key: str, mv: MetricValue, dist: list[float] | None, prev_grade: str | None) -> ScoredMetric:
    """单个指标在板块分布中打分（百分位 + 防抖等级 + 中位数 / 分位统计）。"""
    lower_better = METRICS[key].direction == "lower_better"
    dist = dist or []
    n = len(dist)
    base = ScoredMetric(key, mv, mv.status, None, None, n)
    if n:
        median = quantile(dist, 0.5)
        base.sector_median = median
        base.distribution = {f"p{int(q * 100)}": quantile(dist, q) for q in (0.1, 0.25, 0.5, 0.75, 0.9)}
        if mv.status == "ok" and mv.value is not None and median:
            base.diff_to_median_pct = (mv.value - median) / abs(median) * 100
    if mv.status in ("not_applicable", "missing"):
        return base
    if n < MIN_SAMPLE:
        base.status = "insufficient_sample"
        return base
    if mv.status == "not_meaningful":
        base.percentile = 0.0
    else:
        base.percentile = percentile_of(mv.value, dist, lower_better=lower_better)  # type: ignore[arg-type]
    base.grade = grade_with_hysteresis(base.percentile, prev_grade)
    return base


def score_dimension(dim: str, scored: list[ScoredMetric], prev_grade: str | None, *,
                    expected: int | None = None, accumulating_days: int | None = None) -> DimensionScore:
    """expected：本维度按规则应参与的指标数（EPS 修正积累期只算已到回看期的指标）。"""
    if accumulating_days is not None:
        return DimensionScore(dim, "accumulating", None, None, scored, days_accumulated=accumulating_days)
    total = expected if expected is not None else len(scored)
    part = [s for s in scored if s.percentile is not None]
    if total == 0 or len(part) * 2 < total:
        return DimensionScore(dim, "unavailable", None, None, scored)
    score = round(sum(s.percentile for s in part) / len(part), 1)  # type: ignore[misc]
    return DimensionScore(dim, "ok", score, grade_with_hysteresis(score, prev_grade), scored)


def composite(dims: list[DimensionScore]) -> float | None:
    """可用维度分的等权平均。"""
    usable = [d.score for d in dims if d.status == "ok" and d.score is not None]
    return round(sum(usable) / len(usable), 1) if usable else None


def overall(dims: list[DimensionScore], overall_dist: list[float], n_analysts: int,
            prev_grade: str | None) -> OverallScore:
    """综合等级：综合分在全体中的百分位 → 等级；一票否决与分析师不足处理。"""
    score = composite(dims)
    used = sum(d.status == "ok" for d in dims)
    if score is None:
        return OverallScore(None, None, None, used)
    pct = percentile_of(score, overall_dist, lower_better=False)
    if n_analysts < MIN_ANALYSTS:
        return OverallScore(score, pct, None, used, extra={"reason": "few_analysts"})
    grade = grade_with_hysteresis(pct, prev_grade)
    weak = [d for d in dims if d.status == "ok" and d.score is not None and d.score < CAP_THRESHOLD]
    if weak:
        capped = cap_grade(grade, CAP_CEILING)
        if capped != grade:  # 只有真的被压低才算「封顶」
            return OverallScore(score, pct, capped, used, True, weak[0].key)
    return OverallScore(score, pct, grade, used)


def pick_key_fact(dim: DimensionScore) -> str | None:
    """维度分 ≥ 50 取百分位最高的指标，否则取最低的；优先有真实数值的指标。"""
    part = [s for s in dim.metrics if s.percentile is not None]
    if dim.score is None or not part:
        return None
    real = [s for s in part if s.mv.status == "ok"]
    part = real or part  # 优先有真实数值的指标，「无意义」的信息量低
    if dim.score >= 50:
        return max(part, key=lambda s: s.percentile).key  # type: ignore[arg-type,return-value]
    return min(part, key=lambda s: s.percentile).key  # type: ignore[arg-type,return-value]


def mark_extremes(dims: list[DimensionScore]) -> None:
    """标出分最高 / 最低的维度（首页卡片高亮）。"""
    usable = [d for d in dims if d.status == "ok" and d.score is not None]
    if len(usable) < 2:
        return
    order = {k: i for i, k in enumerate(DIMENSIONS)}
    hi = max(usable, key=lambda d: (d.score, -order[d.key]))
    lo = min(usable, key=lambda d: (d.score, order[d.key]))
    if hi is not lo:
        hi.is_highest = True
        lo.is_lowest = True
