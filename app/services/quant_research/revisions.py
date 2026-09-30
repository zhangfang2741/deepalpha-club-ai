"""EPS 修正：用自有的每日一致预期快照，比较当前值与 30 / 90 天前的值。纯函数。

与 SA 的差异：SA 统计上修 / 下修的分析师人数；我们没有逐分析师数据，改用一致预期均值变化。
变化率在负基数时用 (新 − 旧) / |旧|，亏损收窄算上修。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from app.services.quant_research.metrics import MetricValue

TOLERANCE_DAYS = 7
FULL_DAYS = 90
PARTIAL_DAYS = 30


@dataclass(frozen=True)
class EstimatePoint:
    snapshot_date: date
    fiscal_date: str      # 财年截止日 YYYY-MM-DD，作为同一财年的标识
    eps_avg: float | None
    revenue_avg: float | None
    n_analysts: int = 0


def value_at(history: list[EstimatePoint], fiscal_date: str, target: date, field: str,
             tolerance_days: int = TOLERANCE_DAYS) -> float | None:
    """取 target 当天或之前、相差不超过 tolerance_days 的最近一份快照里的值。"""
    best: EstimatePoint | None = None
    for p in history:
        if p.fiscal_date != fiscal_date or p.snapshot_date > target:
            continue
        if (target - p.snapshot_date).days > tolerance_days:
            continue
        if best is None or p.snapshot_date > best.snapshot_date:
            best = p
    return getattr(best, field) if best else None


def change(new: float | None, old: float | None) -> float | None:
    """变化率 (新 − 旧) / |旧|；旧值为 0 或缺失返回 None。"""
    if new is None or old is None or old == 0:
        return None
    return (new - old) / abs(old)


def accumulated_days(history: list[EstimatePoint], as_of: date) -> int:
    """最早一份快照距今的天数。"""
    if not history:
        return 0
    return (as_of - min(p.snapshot_date for p in history)).days


def revision_status(history: list[EstimatePoint], as_of: date) -> tuple[Literal["ok", "accumulating"], int]:
    """历史不足 30 天为 accumulating，并返回已积累天数。"""
    days = accumulated_days(history, as_of)
    return ("accumulating" if days < PARTIAL_DAYS else "ok"), days


_SPECS = [
    # 每项依次是：指标键、第几财年、快照字段、回看天数
    ("eps_fy1_30d", 1, "eps_avg", 30),
    ("eps_fy1_90d", 1, "eps_avg", 90),
    ("eps_fy2_90d", 2, "eps_avg", 90),
    ("rev_fy1_90d", 1, "revenue_avg", 90),
]


def compute_revisions(history: list[EstimatePoint], as_of: date, fy1_date: str | None,
                      fy2_date: str | None, n_analysts: int, min_analysts: int = 3) -> dict[str, MetricValue]:
    """四项修正指标。历史不够回看天数、分析师不足、找不到对应快照 → missing。"""
    days = accumulated_days(history, as_of)
    out: dict[str, MetricValue] = {}
    for key, fy, field, lookback in _SPECS:
        fiscal = fy1_date if fy == 1 else fy2_date
        if fiscal is None or n_analysts < min_analysts or days < lookback:
            out[key] = MetricValue(None, "missing", [], "change", {"days_accumulated": days})
            continue
        new = value_at(history, fiscal, as_of, field)
        old = value_at(history, fiscal, as_of - timedelta(days=lookback), field)
        c = change(new, old)
        inputs = [("est_new", new), ("est_old", old)]
        meta = {"lookback_days": lookback, "fiscal_date": fiscal, "days_accumulated": days}
        out[key] = MetricValue(c, "ok" if c is not None else "missing", inputs, "change", meta)
    return out
