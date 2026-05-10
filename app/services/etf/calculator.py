"""ETF 资金流计算函数。

资金流计算公式：
  CLV = (2×adjClose - high - low) / (high - low + 1e-9)
  Flow = CLV × adjClose × volume
  Intensity = Z-score(Flow)  跨全部 ETF × 全部交易日标准化
"""

import datetime
import math
from typing import List


def compute_clv(adj_close: float, high: float, low: float) -> float:
    """计算 Close Location Value。

    CLV = (2×adjClose - high - low) / (high - low + 1e-9)
    范围 [-1, 1]，1e-9 避免 high=low 时除零。

    Args:
        adj_close: 调整后收盘价
        high: 最高价
        low: 最低价

    Returns:
        CLV 值，范围 [-1, 1]
    """
    return (2 * adj_close - high - low) / (high - low + 1e-9)


def compute_flow(clv: float, adj_close: float, volume: int) -> float:
    """计算资金流原始值。

    Flow = CLV × adjClose × volume

    Args:
        clv: Close Location Value
        adj_close: 调整后收盘价
        volume: 成交量

    Returns:
        资金流原始值
    """
    return clv * adj_close * volume


def z_score_normalize(flows: List[float]) -> List[float]:
    """对 flows 列表做 Z-score 标准化。

    标准差为 0（常数序列）时返回全零列表。

    Args:
        flows: 资金流原始值列表

    Returns:
        标准化后的列表
    """
    if not flows:
        return []
    n = len(flows)
    mean = sum(flows) / n
    variance = sum((f - mean) ** 2 for f in flows) / n
    std = math.sqrt(variance)
    if std < 1e-9 or not math.isfinite(std):
        return [0.0] * n
    return [(f - mean) / std for f in flows]


def date_label(date_str: str, granularity: str) -> str:
    """将 'YYYY-MM-DD' 转换为对应粒度的标签。

    Args:
        date_str: ISO 格式日期字符串
        granularity: 粒度，'day' | 'week' | 'month'

    Returns:
        对应粒度的标签字符串
    """
    d = datetime.date.fromisoformat(date_str)
    if granularity == "week":
        iso = d.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    if granularity == "month":
        return f"{d.year}-{d.month:02d}"
    return date_str  # day
