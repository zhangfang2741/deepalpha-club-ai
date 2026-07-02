"""一目均衡表基础线计算：转换线 / 基准线 / 先行带 A·B / 迟行线。

所有函数只做纯数值计算，返回与输入 K 线等长、按 bar 下标对齐的列表；
数据不足周期处用 None 占位。时间轴平移（先行带前移、迟行线后移）在
analyzer 层组装，这里保持无状态。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LinePoint:
    """时间序列上的一个点（某条线在某时间的取值）。"""

    time: str
    value: float


def _period_mid(bars: list[dict], end_idx: int, period: int) -> float | None:
    """以 end_idx 为最后一根、回看 period 根的 (最高价 + 最低价) / 2。

    数据不足 period 根时返回 None（一目均衡表称之为「中值」）。
    """
    if period <= 0 or end_idx < period - 1:
        return None
    window = bars[end_idx - period + 1 : end_idx + 1]
    hi = max(float(b["high"]) for b in window)
    lo = min(float(b["low"]) for b in window)
    return (hi + lo) / 2.0


def conversion_line(bars: list[dict], period: int = 9) -> list[float | None]:
    """转换线（Tenkan-sen）：近 period 根中值，默认 9。"""
    return [_period_mid(bars, i, period) for i in range(len(bars))]


def base_line(bars: list[dict], period: int = 26) -> list[float | None]:
    """基准线（Kijun-sen）：近 period 根中值，默认 26。"""
    return [_period_mid(bars, i, period) for i in range(len(bars))]


def leading_span_a(
    conversion: list[float | None], base: list[float | None]
) -> list[float | None]:
    """先行带 A（Senkou Span A）：(转换线 + 基准线) / 2（未平移的原始值）。"""
    out: list[float | None] = []
    for c, b in zip(conversion, base, strict=True):
        out.append((c + b) / 2.0 if c is not None and b is not None else None)
    return out


def leading_span_b(bars: list[dict], period: int = 52) -> list[float | None]:
    """先行带 B（Senkou Span B）：近 period 根中值（未平移的原始值），默认 52。"""
    return [_period_mid(bars, i, period) for i in range(len(bars))]
