"""图表指标：EMA、BOLL（均线见 ma.py）。

和均线一样：按含预热的完整前复权**原始 K 线收盘**算，输出时再按合并 K 线的 `end_time` 对齐
（`app/api/v1/chan.py` 的 `_ema_out` / `_boll_out`）。新增指标照这个模式加：这里写 calc_xxx + 对齐函数，
analyzer 里在结构判断前算好，API 加字段，iOS 在 `ChartIndicator` 登记（见 CLAUDE.md「图表指标栏」）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.services.chan.ma import MAData

EMA_PERIODS = (12, 26)
BOLL_PERIOD = 20
BOLL_MULT = 2.0

# 用户自定义参数的范围（App「指标设置」）。线数上限 = App 给每组线准备的颜色数。
PERIOD_MIN, PERIOD_MAX = 2, 250
MA_MAX_LINES = 3
EMA_MAX_LINES = 2
BOLL_MULT_MIN, BOLL_MULT_MAX = 0.5, 5.0


@dataclass(frozen=True)
class IndicatorParams:
    """用户自定义的指标参数；None = 用默认（均线按周期默认，见 ma.MA_PERIODS）。"""

    ma: tuple[int, ...] | None = None
    ema: tuple[int, ...] | None = None
    boll: tuple[int, float] | None = None


def parse_periods(raw: str | None, *, max_count: int) -> tuple[int, ...] | None:
    """「5,20,60」→ (5, 20, 60)（升序去重）。空 / 非法 / 越界一律返回 None（调用方回退默认，不报错）。"""
    if not raw:
        return None
    try:
        periods = sorted({int(p) for p in raw.split(",") if p.strip()})
    except ValueError:
        return None
    if not periods or len(periods) > max_count:
        return None
    if any(p < PERIOD_MIN or p > PERIOD_MAX for p in periods):
        return None
    return tuple(periods)


def parse_boll(raw: str | None) -> tuple[int, float] | None:
    """「20,2」→ (20, 2.0)。非法 / 越界返回 None（回退默认）。"""
    if not raw:
        return None
    parts = raw.split(",")
    if len(parts) != 2:
        return None
    try:
        period, mult = int(parts[0]), float(parts[1])
    except ValueError:
        return None
    if not (PERIOD_MIN <= period <= PERIOD_MAX) or not (BOLL_MULT_MIN <= mult <= BOLL_MULT_MAX):
        return None
    return period, mult


def calc_ema(bars: list[dict], periods: tuple[int, ...]) -> MAData:
    """指数移动平均：前 n 根简单平均作种子（TA-Lib 口径，与项目里的 MACD 同口径），不足 n 根记 None。"""
    closes = [float(b["close"]) for b in bars]
    series: dict[int, list[float | None]] = {}
    for n in periods:
        out: list[float | None] = [None] * len(closes)
        if len(closes) >= n:
            k = 2.0 / (n + 1)
            prev = sum(closes[:n]) / n
            out[n - 1] = round(prev, 4)
            for i in range(n, len(closes)):
                prev = closes[i] * k + prev * (1 - k)
                out[i] = round(prev, 4)
        series[n] = out
    return MAData(periods=periods, times=[b["time"] for b in bars], series=series)


@dataclass
class BollData:
    period: int
    mult: float
    times: list[str]
    upper: list[float | None] = field(default_factory=list)
    mid: list[float | None] = field(default_factory=list)
    lower: list[float | None] = field(default_factory=list)


def calc_boll(bars: list[dict], period: int = BOLL_PERIOD, mult: float = BOLL_MULT) -> BollData:
    """布林带：中轨 = period 日简单均线，上 / 下轨 = 中轨 ± mult 倍**总体**标准差（国内行情软件口径）。"""
    closes = [float(b["close"]) for b in bars]
    data = BollData(period=period, mult=mult, times=[b["time"] for b in bars])
    for i in range(len(closes)):
        if i + 1 < period:
            data.upper.append(None)
            data.mid.append(None)
            data.lower.append(None)
            continue
        window = closes[i + 1 - period:i + 1]
        mean = sum(window) / period
        std = math.sqrt(sum((x - mean) ** 2 for x in window) / period)
        data.mid.append(round(mean, 4))
        data.upper.append(round(mean + mult * std, 4))
        data.lower.append(round(mean - mult * std, 4))
    return data


def align_boll(boll: BollData, times: list[str]) -> BollData:
    """按时间取值，对齐到给定时间序列（合并 K 线）；找不到的记 None。"""
    index = {t: i for i, t in enumerate(boll.times)}

    def pick(values: list[float | None]) -> list[float | None]:
        return [values[index[t]] if t in index else None for t in times]

    return BollData(period=boll.period, mult=boll.mult, times=list(times),
                    upper=pick(boll.upper), mid=pick(boll.mid), lower=pick(boll.lower))
