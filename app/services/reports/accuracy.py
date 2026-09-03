"""准确率口径（第一版：方向 + 时限）。

判定一篇报告是否命中：报告声明方向 direction 与时限 horizon_days，平台在发布当时
记录 mark_price；到期时取到期日收盘价 price_at_horizon，计算实际收益率与是否命中。

- 看多 BULLISH：actual_return_pct >= hit_threshold_pct
- 看空 BEARISH：actual_return_pct <= -hit_threshold_pct
- 中性 NEUTRAL：abs(actual_return_pct) <= neutral_band_pct

准确率 = 命中数 / 已到期报告数，只统计已结算（RESOLVED）报告。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional

from app.models.report import (
    DIRECTION_BEARISH,
    DIRECTION_BULLISH,
    DIRECTION_NEUTRAL,
)

# 方向命中门槛（%）：0 表示严格方向（只要涨/跌就算）
DEFAULT_HIT_THRESHOLD_PCT = 0.0
# 中性判定带宽（%）：涨跌幅绝对值不超过此值算中性命中
DEFAULT_NEUTRAL_BAND_PCT = 3.0


def horizon_end_date(mark_date: str, horizon_days: int) -> str:
    """计算计划到期日（mark_date + horizon_days 自然日），返回 YYYY-MM-DD。"""
    base = datetime.strptime(mark_date, "%Y-%m-%d")
    return (base + timedelta(days=horizon_days)).strftime("%Y-%m-%d")


def compute_return_pct(mark_price: float, price_at_horizon: float) -> float:
    """实际收益率（%）。"""
    if mark_price <= 0:
        raise ValueError("mark_price 必须为正")
    return (price_at_horizon - mark_price) / mark_price * 100.0


def is_hit(
    direction: str,
    return_pct: float,
    hit_threshold_pct: float = DEFAULT_HIT_THRESHOLD_PCT,
    neutral_band_pct: float = DEFAULT_NEUTRAL_BAND_PCT,
) -> bool:
    """给定方向与实际收益率，判断是否命中。"""
    if direction == DIRECTION_BULLISH:
        return return_pct >= hit_threshold_pct
    if direction == DIRECTION_BEARISH:
        return return_pct <= -hit_threshold_pct
    if direction == DIRECTION_NEUTRAL:
        return abs(return_pct) <= neutral_band_pct
    raise ValueError(f"未知方向：{direction}")


def evaluate_direction(
    direction: str,
    mark_price: float,
    price_at_horizon: float,
    hit_threshold_pct: float = DEFAULT_HIT_THRESHOLD_PCT,
    neutral_band_pct: float = DEFAULT_NEUTRAL_BAND_PCT,
) -> tuple[float, bool]:
    """回测一篇报告：返回 (实际收益率%, 是否命中)。"""
    return_pct = compute_return_pct(mark_price, price_at_horizon)
    hit = is_hit(direction, return_pct, hit_threshold_pct, neutral_band_pct)
    return return_pct, hit


@dataclass
class AnalystAccuracy:
    """经纪人准确率聚合结果。"""

    resolved_count: int
    correct_count: int
    accuracy: Optional[float]  # 命中率 [0,1]，无已到期报告时为 None
    avg_return_pct: Optional[float]  # 已到期报告平均实际收益率，无则 None


@dataclass
class OutcomeSample:
    """参与聚合的单条回测样本。"""

    is_correct: Optional[bool]
    actual_return_pct: Optional[float]


def compute_analyst_accuracy(outcomes: Iterable[OutcomeSample]) -> AnalystAccuracy:
    """由若干已结算回测样本聚合出经纪人准确率与平均收益。

    只统计 is_correct 非空（已结算）的样本；未到期样本自动忽略。
    """
    resolved = [o for o in outcomes if o.is_correct is not None]
    resolved_count = len(resolved)
    correct_count = sum(1 for o in resolved if o.is_correct)

    accuracy = correct_count / resolved_count if resolved_count else None

    returns = [o.actual_return_pct for o in resolved if o.actual_return_pct is not None]
    avg_return = sum(returns) / len(returns) if returns else None

    return AnalystAccuracy(
        resolved_count=resolved_count,
        correct_count=correct_count,
        accuracy=accuracy,
        avg_return_pct=avg_return,
    )
