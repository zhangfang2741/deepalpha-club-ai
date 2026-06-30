"""缠论中枢识别：连续3段走势的价格重叠区域"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.chan.segment import Segment
from app.services.chan.stroke import Stroke


@dataclass
class Pivot:
    """中枢：至少3段价格走势形成的重叠区域"""
    zg: float    # 中枢高点（区间上沿）
    zd: float    # 中枢低点（区间下沿）
    gg: float    # 中枢最高点（进入中枢的最高价）
    dd: float    # 中枢最低点（进入中枢的最低价）
    start_time: str
    end_time: str
    level: Literal["stroke", "segment"]  # 笔级别 or 线段级别
    elements: list  # 构成中枢的笔或线段

    @property
    def height(self) -> float:
        return self.zg - self.zd

    @property
    def is_valid(self) -> bool:
        return self.zg > self.zd


def _find_pivots_from_elements(elements: list, level: Literal["stroke", "segment"]) -> list[Pivot]:
    """通用中枢识别：从任意走势元素序列中识别中枢"""
    if len(elements) < 3:
        return []

    pivots: list[Pivot] = []
    i = 0

    while i <= len(elements) - 3:
        e0, e1, e2 = elements[i], elements[i + 1], elements[i + 2]

        # 三段走势的价格重叠区域
        zg = min(e0.high, e1.high, e2.high)
        zd = max(e0.low, e1.low, e2.low)

        if zg <= zd:
            i += 1
            continue

        # 有效中枢形成
        pivot_elements = [e0, e1, e2]
        gg = max(e0.high, e1.high, e2.high)
        dd = min(e0.low, e1.low, e2.low)

        # 中枢延伸：后续走势仍在中枢区间内
        j = i + 3
        while j < len(elements):
            ej = elements[j]
            if ej.low <= zg and ej.high >= zd:
                # 走势仍在中枢内，延伸中枢
                zg = min(zg, ej.high)
                zd = max(zd, ej.low)
                gg = max(gg, ej.high)
                dd = min(dd, ej.low)
                pivot_elements.append(ej)
                j += 1
            else:
                break

        pivot = Pivot(
            zg=zg,
            zd=zd,
            gg=gg,
            dd=dd,
            start_time=pivot_elements[0].start_time,
            end_time=pivot_elements[-1].end_time,
            level=level,
            elements=pivot_elements,
        )
        pivots.append(pivot)
        i = j  # 从中枢结束后的下一个元素继续

    return pivots


def find_stroke_pivots(strokes: list[Stroke]) -> list[Pivot]:
    """识别笔级别中枢"""
    return _find_pivots_from_elements(strokes, level="stroke")


def find_segment_pivots(segments: list[Segment]) -> list[Pivot]:
    """识别线段级别中枢"""
    return _find_pivots_from_elements(segments, level="segment")
