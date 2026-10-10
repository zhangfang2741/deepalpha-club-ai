"""13 档字母等级（指标 / 维度 / 综合三层同一把尺子）、板块百分位、防抖动。纯函数。"""

from __future__ import annotations

from bisect import bisect_left, bisect_right

BANDS: list[tuple[float, str]] = [
    (93, "A+"), (86, "A"), (80, "A-"), (73, "B+"), (66, "B"), (60, "B-"),
    (53, "C+"), (46, "C"), (40, "C-"), (33, "D+"), (26, "D"), (20, "D-"), (0, "F"),
]
GRADE_ORDER: list[str] = [g for _, g in BANDS]
# 越过旧等级区间边界至少这么多分才换等级，避免边界上的股票每天来回跳
HYSTERESIS = 2.0

_LOWER = {g: lo for lo, g in BANDS}
_UPPER = {g: (BANDS[i - 1][0] if i else 100.0) for i, (_, g) in enumerate(BANDS)}


def grade_for(p: float) -> str:
    """百分位 → 等级。"""
    return next(g for lo, g in BANDS if p >= lo)


def grade_with_hysteresis(p: float, prev: str | None) -> str:
    """旧等级区间向两侧各放宽 HYSTERESIS 分；仍在放宽后的区间内就沿用旧等级。"""
    if prev is None or prev not in _LOWER:
        return grade_for(p)
    lo, hi = _LOWER[prev], _UPPER[prev]
    lo_bound = lo - HYSTERESIS if lo > 0 else float("-inf")
    hi_bound = hi + HYSTERESIS if hi < 100 else float("inf")
    if lo_bound < p < hi_bound:
        return prev
    return grade_for(p)


def cap_grade(grade: str, ceiling: str) -> str:
    """等级不高于 ceiling（一票否决用）。"""
    return grade if GRADE_ORDER.index(grade) >= GRADE_ORDER.index(ceiling) else ceiling


def percentile_of(value: float, sorted_values: list[float], *, lower_better: bool) -> float:
    """计算 value 在 sorted_values（升序）中的百分位 0~100，方向统一成越高越好。

    越高越好：不大于它的比例；越低越好：不小于它的比例。**并列取平均位次**：m 家并列时，它们占据的 m 个位次取中间值，
    而不是都拿最高位次——否则净现金（净负债比 = 0）、不烧钱（年数封顶）这类大量公司并列在极值的指标，
    会让几乎所有公司都显示「高于板块 100% 的公司」，也把对应维度整体抬高。没有并列时与「不大于它的比例」完全一致。
    样本为空时返回 50。
    """
    n = len(sorted_values)
    if n == 0:
        return 50.0
    lt, le = bisect_left(sorted_values, value), bisect_right(sorted_values, value)
    m = le - lt                                   # 与 value 并列的家数（样本外的值 m = 0）
    if lower_better:
        worse_or_tied = n - lt                    # 不小于它的家数
        rank = worse_or_tied - (m - 1) / 2 if m else worse_or_tied
    else:
        rank = lt + (m + 1) / 2 if m else le      # 位次：严格小于它的家数 + 并列者的平均位次
    return round(rank / n * 100, 1)
