"""合并 K 线所含原始 K 线的真实最高 / 最低价。

缠论去包含后，合并 K 线的高低点是按方向合并出来的（上行取高点的最大、低点的最大；下行取高点的最小、低点的最小），
比原始 K 线的影线短。SMC / 威科夫是按原始 K 线算的，位置要落在真实影线上：打开这两个指标时，App 的影线用这里算出的
原始最高 / 最低价画，结构线和订单块 / 缺口的边才碰得到影线。缠论图层的画法不受影响。
"""
from __future__ import annotations

from app.services.chan.fractal import MergedCandle


def raw_extremes(bars: list[dict], candles: list[MergedCandle]) -> list[tuple[float, float]]:
    """每根合并 K 线对应的 (原始最高, 原始最低)。

    `MergedCandle.raw_start / raw_end` 就是所含原始 K 线在 `bars` 里的下标（含两端；BABA / NVDA / 0700.HK 共 1362 根
    逐根核对过开盘 / 收盘 / 结束时间，下标偏移为 0），首笔确认前被 czsc 丢掉的前导 K 线自然不在任何一根里。
    结果不会比合并 K 线自己的高低点更窄；下标越界（不该发生）时退回合并 K 线自己的高低点。
    """
    n = len(bars)
    out: list[tuple[float, float]] = []
    for c in candles:
        hi, lo = c.high, c.low
        for i in range(max(0, c.raw_start), min(n - 1, c.raw_end) + 1):
            hi = max(hi, float(bars[i]["high"]))
            lo = min(lo, float(bars[i]["low"]))
        out.append((hi, lo))
    return out
