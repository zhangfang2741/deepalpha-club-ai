"""均线（MA）：简单移动平均，按原始前复权收盘价算，供 App 主图叠加。

日线 / 30 分钟用 5、20、60，周线用 5、10、20。必须在含预热的完整 K 线上算：
显示起点之前的 K 线也参与平均，显示区第一根起就有值；再按合并 K 线的时间对齐后输出。
"""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_PERIODS = (5, 20, 60)
MA_PERIODS: dict[str, tuple[int, ...]] = {
    "daily": (5, 20, 60),
    "30min": (5, 20, 60),
    "weekly": (5, 10, 20),
}


@dataclass
class MAData:
    periods: tuple[int, ...]
    times: list[str]  # 与原始 K 线一一对应
    series: dict[int, list[float | None]] = field(default_factory=dict)  # 不足 n 根的前 n-1 个为 None


def calc_ma(bars: list[dict], periods: tuple[int, ...]) -> MAData:
    """每根 K 线的 n 日简单平均收盘价；不足 n 根记 None。"""
    closes = [float(b["close"]) for b in bars]
    prefix = [0.0]
    for c in closes:
        prefix.append(prefix[-1] + c)
    series: dict[int, list[float | None]] = {}
    for n in periods:
        series[n] = [
            round((prefix[i + 1] - prefix[i + 1 - n]) / n, 4) if i + 1 >= n else None
            for i in range(len(closes))
        ]
    return MAData(periods=periods, times=[b["time"] for b in bars], series=series)


def align_to_times(ma: MAData, times: list[str]) -> dict[int, list[float | None]]:
    """按时间取值，对齐到给定时间序列（合并 K 线）；时间轴里找不到的记 None。"""
    index = {t: i for i, t in enumerate(ma.times)}
    out: dict[int, list[float | None]] = {}
    for n, values in ma.series.items():
        out[n] = [values[index[t]] if t in index else None for t in times]
    return out
