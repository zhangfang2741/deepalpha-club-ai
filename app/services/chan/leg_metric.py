"""背驰度量（可插拔）：比较 c 段（离开中枢 B）与 b 段（A、B 之间）的力度。

缠论原文的趋势背驰度量是 MACD 红绿柱面积（macd_area）；项目早期用的价差 / 量能 / 时长
（force）保留为另一种实现。严格口径只通过 DivergenceMetric 接口取度量，换度量 = 改配置
CHAN_DIVERGENCE_METRIC，不动判定流程。

对外（API / DivergenceResult）永远同一套字段：price_ratio / volume_ratio / length_ratio 三项
参考比值任何度量都填；area_ratio 只有 MACD 面积度量能算时才填。强弱分档统一用度量给出的
primary_ratio（classify_strength 的阈值取自价差比，换成面积比后须重新标定）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.services.chan.divergence import MACDData
from app.services.chan.stroke import Stroke


@dataclass(frozen=True)
class LegForce:
    """一段走势（若干笔）的力度原料。area=None 表示没有 MACD 数据、算不出面积。"""
    price: float
    volume: float
    length: int
    area: float | None


@dataclass(frozen=True)
class LegComparison:
    """c 段对 b 段的比较结果：是否背驰 + 各项比值（primary_ratio 决定强弱分档）。"""
    diverged: bool
    primary_ratio: float
    price_ratio: float
    volume_ratio: float
    length_ratio: float
    area_ratio: float | None


def macd_area(macd: MACDData, start: str, end: str, is_down: bool) -> float:
    """[start, end] 内与走势同向的 MACD 柱面积（下跌取绿柱绝对值之和、上涨取红柱之和）。"""
    total = 0.0
    for t, v in zip(macd.times, macd.bar, strict=False):
        if start <= t <= end and ((v < 0) if is_down else (v > 0)):
            total += abs(v)
    return total


def leg_force(legs: list[Stroke], macd: MACDData | None) -> LegForce:
    """若干连续同向走势笔合成一段的力度：价差 = 首笔起点到末笔终点。"""
    is_down = legs[-1].end_price < legs[0].start_price
    area = macd_area(macd, legs[0].start_time, legs[-1].end_time, is_down) if macd is not None else None
    return LegForce(
        price=abs(legs[0].start_price - legs[-1].end_price),
        volume=sum(float(st.power_volume) for st in legs),
        length=sum(int(st.length) for st in legs),
        area=area,
    )


def _ratio(num: float, den: float) -> float:
    return round(num / den, 2) if den > 0 else 1.0


class DivergenceMetric(Protocol):
    @property
    def name(self) -> str: ...

    def compare(self, c: LegForce, b: LegForce) -> LegComparison | None:
        """比较 c 段与 b 段；该度量算不出来（缺数据）返回 None。"""
        ...


@dataclass(frozen=True)
class MacdAreaMetric:
    """缠论原文：c 段 MACD 面积小于 b 段即背驰（价格创新极值由调用方保证）。"""
    name: str = "macd_area"

    def compare(self, c: LegForce, b: LegForce) -> LegComparison | None:
        if c.area is None or b.area is None or b.area <= 0 or b.price <= 0:
            return None
        area = _ratio(c.area, b.area)
        return LegComparison(
            diverged=area < 1, primary_ratio=area, price_ratio=_ratio(c.price, b.price),
            volume_ratio=_ratio(c.volume, b.volume), length_ratio=_ratio(c.length, b.length), area_ratio=area,
        )


@dataclass(frozen=True)
class ForceMetric:
    """价差 / 量能 / 时长：价差更弱，且量能或时长至少一项更弱（与 czsc 一类同一判据）。"""
    name: str = "force"

    def compare(self, c: LegForce, b: LegForce) -> LegComparison | None:
        if b.price <= 0:
            return None
        price, volume, length = _ratio(c.price, b.price), _ratio(c.volume, b.volume), _ratio(c.length, b.length)
        area = _ratio(c.area, b.area) if c.area is not None and b.area else None
        return LegComparison(
            diverged=price < 1 and (volume < 1 or length < 1), primary_ratio=price,
            price_ratio=price, volume_ratio=volume, length_ratio=length, area_ratio=area,
        )


DIVERGENCE_METRICS: dict[str, DivergenceMetric] = {m.name: m for m in (MacdAreaMetric(), ForceMetric())}
DEFAULT_METRIC = "macd_area"


def get_metric(name: str | None) -> DivergenceMetric:
    """按名字取背驰度量；未知 / 空回退默认（原文：MACD 面积）。"""
    return DIVERGENCE_METRICS.get(name or DEFAULT_METRIC) or DIVERGENCE_METRICS[DEFAULT_METRIC]
