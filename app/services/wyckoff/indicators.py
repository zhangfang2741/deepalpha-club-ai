"""威科夫分析基础指标：摆动点（swing）识别、均量、价差统计。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Swing:
    """价格摆动极值点（局部高点 / 低点）。"""

    kind: str      # "high" | "low"
    idx: int       # 在 bars 中的下标
    time: str
    price: float   # 高点用 high，低点用 low
    volume: float


@dataclass
class VolumeStats:
    """成交量统计，用于识别高潮量 / 缩量。"""

    mean: float
    std: float
    values: list[float]

    def zscore(self, idx: int) -> float:
        """某根 K 线成交量相对均值的标准分（std 为 0 时返回 0）。"""
        if self.std <= 0 or idx < 0 or idx >= len(self.values):
            return 0.0
        return (self.values[idx] - self.mean) / self.std

    def ratio(self, idx: int) -> float:
        """某根 K 线成交量 / 平均成交量（均值为 0 时返回 1）。"""
        if self.mean <= 0 or idx < 0 or idx >= len(self.values):
            return 1.0
        return self.values[idx] / self.mean


def sma(values: list[float], period: int) -> list[float]:
    """简单移动平均，长度与输入一致（不足周期处用累计均值）。"""
    out: list[float] = []
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= period:
            running -= values[i - period]
            out.append(running / period)
        else:
            out.append(running / (i + 1))
    return out


def volume_stats(bars: list[dict]) -> VolumeStats:
    """整体成交量均值与标准差。"""
    vols = [float(b.get("volume", 0) or 0) for b in bars]
    n = len(vols)
    if n == 0:
        return VolumeStats(mean=0.0, std=0.0, values=[])
    mean = sum(vols) / n
    var = sum((v - mean) ** 2 for v in vols) / n
    return VolumeStats(mean=mean, std=var ** 0.5, values=vols)


def find_swings(bars: list[dict], left: int = 3, right: int = 3) -> list[Swing]:
    """基于左右窗口识别摆动高低点（分型）。

    swing high：比左侧 left 根都高（含相等）且严格高于右侧 right 根；
    swing low：比左侧 left 根都低（含相等）且严格低于右侧 right 根。
    以左含等、右取严的方式打破平顶 / 平底的重复识别。
    """
    swings: list[Swing] = []
    n = len(bars)
    for i in range(left, n - right):
        hi = bars[i]["high"]
        lo = bars[i]["low"]
        left_hi = all(bars[j]["high"] <= hi for j in range(i - left, i))
        right_hi = all(bars[j]["high"] < hi for j in range(i + 1, i + right + 1))
        if left_hi and right_hi:
            swings.append(
                Swing(kind="high", idx=i, time=bars[i]["time"], price=hi,
                      volume=float(bars[i].get("volume", 0) or 0))
            )
            continue
        left_lo = all(bars[j]["low"] >= lo for j in range(i - left, i))
        right_lo = all(bars[j]["low"] > lo for j in range(i + 1, i + right + 1))
        if left_lo and right_lo:
            swings.append(
                Swing(kind="low", idx=i, time=bars[i]["time"], price=lo,
                      volume=float(bars[i].get("volume", 0) or 0))
            )
    return swings


def bar_spread(bar: dict) -> float:
    """单根 K 线价差（high - low）。"""
    return float(bar["high"]) - float(bar["low"])


def close_progress(bar: dict) -> float:
    """收盘相对开盘的涨跌幅（close - open）。"""
    return float(bar["close"]) - float(bar["open"])
