"""快照衍生的变化率/排名——纯函数，把「水平」信号升级为「变化率」信号。

输入为历史快照序列，无历史时返回 None（调用方回退到水平口径）。
"""
import datetime
from typing import Optional


def pct_change(current: Optional[float], past: Optional[float]) -> Optional[float]:
    """相对变化百分比；past 为 0 或缺失返回 None。"""
    if current is None or not past:
        return None
    return round((current - past) / past * 100, 1)


def iv_rank(current: Optional[float], history: list[Optional[float]], min_points: int = 20) -> Optional[float]:
    """IV Rank：current 在历史 [min, max] 中的百分位（0–100）。

    历史点不足 min_points 或区间退化时返回 None。
    """
    if current is None:
        return None
    vals = [v for v in history if v is not None and v > 0]
    if len(vals) < min_points:
        return None
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        return None
    return round((current - lo) / (hi - lo) * 100, 1)


def value_days_ago(
    points: list[tuple[str, Optional[float]]], days_ago: int, tolerance: int = 12
) -> Optional[float]:
    """从 (date_iso, value) 序列中取最接近「days_ago 天前」的值（容差内）。"""
    target = datetime.date.today() - datetime.timedelta(days=days_ago)
    best: Optional[float] = None
    best_diff: Optional[int] = None
    for d, v in points:
        if v is None:
            continue
        try:
            diff = abs((datetime.date.fromisoformat(d) - target).days)
        except ValueError:
            continue
        if diff <= tolerance and (best_diff is None or diff < best_diff):
            best, best_diff = v, diff
    return best
