"""共享的 RSI(Wilder 平滑) 计算。

供 industry_panic（行业 ETF 情绪）和 panic_index（三地恐慌贪婪指数）两处复用，
避免同一套算法维护两份实现。
"""
from __future__ import annotations

from typing import Optional


def rsi_series(closes: list[float], period: int = 14) -> list[Optional[float]]:
    """Wilder 平滑 RSI 序列，长度与 closes 相同，前 period 个为 None。"""
    n = len(closes)
    result: list[Optional[float]] = [None] * n
    if n <= period:
        return result

    gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, n)]
    losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, n)]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def _rsi(ag: float, al: float) -> float:
        if al == 0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + ag / al)

    result[period] = _rsi(avg_gain, avg_loss)

    for i in range(period, n - 1):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        result[i + 1] = _rsi(avg_gain, avg_loss)

    return result
