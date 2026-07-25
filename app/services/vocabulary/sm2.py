"""SM-2 间隔重复算法：根据复习评分计算下一次复习状态。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

MIN_EASINESS_FACTOR = 2.13
FUZZY_INTERVAL_DAYS = 1
UNKNOWN_INTERVAL_DAYS = 1
KNOWN_STATUS_INTERVAL_THRESHOLD_DAYS = 21


@dataclass
class SM2Result:
    """一次复习后的新状态。"""

    repetition_count: int
    easiness_factor: float
    interval_days: int
    next_review_at: datetime
    status: str  # "new" | "fuzzy" | "known"


def apply_review(
    *,
    rating: int,
    repetition_count: int,
    easiness_factor: float,
    interval_days: int,
    now: datetime | None = None,
) -> SM2Result:
    """根据本次评分计算新的 SM-2 状态。

    Args:
        rating: 0（不认识）/ 1（模糊）/ 2（认识）
        repetition_count: 当前连续「认识」次数
        easiness_factor: 当前难度系数
        interval_days: 当前复习间隔（天）
        now: 当前时间，默认取 UTC now（测试可注入固定时间）

    Returns:
        SM2Result: 更新后的状态

    Raises:
        ValueError: rating 不在 0/1/2 范围内
    """
    if rating not in (0, 1, 2):
        raise ValueError(f"invalid rating: {rating}")

    current_time = now or datetime.now(UTC)

    if rating == 0:
        new_repetition = 0
        new_interval = UNKNOWN_INTERVAL_DAYS
        new_ef = easiness_factor
        status = "new"
    elif rating == 1:
        new_repetition = repetition_count
        new_interval = FUZZY_INTERVAL_DAYS
        new_ef = max(MIN_EASINESS_FACTOR, round(easiness_factor - 0.15, 2))
        status = "fuzzy"
    else:  # rating == 2
        new_repetition = repetition_count + 1
        new_ef = max(MIN_EASINESS_FACTOR, round(easiness_factor + 0.1, 2))
        if new_repetition == 1:
            new_interval = 1
        elif new_repetition == 2:
            new_interval = 6
        else:
            new_interval = round(interval_days * new_ef)
        status = "known" if new_interval >= KNOWN_STATUS_INTERVAL_THRESHOLD_DAYS else "fuzzy"

    next_review_at = current_time + timedelta(days=new_interval)

    return SM2Result(
        repetition_count=new_repetition,
        easiness_factor=new_ef,
        interval_days=new_interval,
        next_review_at=next_review_at,
        status=status,
    )
