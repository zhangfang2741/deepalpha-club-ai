"""缠论线段识别：至少3笔构成，特征序列分型判断结束"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.services.chan.stroke import Stroke


@dataclass
class Segment:
    """线段：由至少3笔（同向）构成的走势"""
    direction: Literal["up", "down"]
    strokes: list[Stroke] = field(default_factory=list)
    # 线段是否已确认：最后一条线段的结束需后续笔/特征序列确认
    confirmed: bool = True

    @property
    def start_time(self) -> str:
        return self.strokes[0].start_time if self.strokes else ""

    @property
    def end_time(self) -> str:
        return self.strokes[-1].end_time if self.strokes else ""

    @property
    def start_price(self) -> float:
        return self.strokes[0].start_price if self.strokes else 0.0

    @property
    def end_price(self) -> float:
        return self.strokes[-1].end_price if self.strokes else 0.0

    @property
    def high(self) -> float:
        return max(s.high for s in self.strokes) if self.strokes else 0.0

    @property
    def low(self) -> float:
        return min(s.low for s in self.strokes) if self.strokes else 0.0

    @property
    def amplitude(self) -> float:
        return abs(self.end_price - self.start_price)

    @property
    def stroke_count(self) -> int:
        return len(self.strokes)


def find_segments(strokes: list[Stroke]) -> list[Segment]:
    """从笔序列识别线段（基于索引，不依赖 Stroke 的值相等）。

    算法（特征序列的实用简化版）：
    - 线段至少由3笔构成，方向由第一笔决定（奇数位笔与线段同向，偶数位笔为回调）。
    - 确立：s0(同向)→s1(反向)→s2(同向)，且 s2 越过 s0 的极值
      （上升需创新高、下降需创新低）。
    - 延伸：其后每对（回调笔, 同向推动笔）中，推动笔继续创新极值则线段延伸。
    - 结束（任一触发即止）：
        · 推动笔未能创出新极值（特征序列出现反向分型）；或
        · 回调笔收复了线段起点（上升段回调跌破起点 / 下降段反弹升破起点）——
          此时走势已反向，线段绝不能吞没这段（例如下降线段吞进一段创出新高的走势）。

    以整数索引跟踪段内笔，避免旧实现用 list.index()/in 依赖 dataclass 值相等，
    在存在等值笔时把索引匹配到错误位置。
    """
    if len(strokes) < 3:
        return []

    segments: list[Segment] = []
    i = 0
    n = len(strokes)

    while i <= n - 3:
        s0, s1, s2 = strokes[i], strokes[i + 1], strokes[i + 2]

        # 方向校验：s0/s2 同向，s1 反向
        if s0.direction != s2.direction or s0.direction == s1.direction:
            i += 1
            continue

        direction = s0.direction
        # 确立条件：s2 必须越过 s0 的极值
        if direction == "up" and s2.end_price <= s0.end_price:
            i += 1
            continue
        if direction == "down" and s2.end_price >= s0.end_price:
            i += 1
            continue

        end = i + 2                    # 段内最后一笔（同向）的索引
        seg_extreme = s2.end_price     # 线段当前极值
        origin = s0.start_price        # 线段起点价（被反向收复即结束）

        # 向后延伸：j 指向同向推动笔，j-1 指向其前的反向回调笔
        j = end + 2
        while j < n:
            push = strokes[j]
            retrace = strokes[j - 1]
            if push.direction != direction:
                break
            # 回调收复线段起点 → 线段被破坏，结束于当前 end
            if direction == "up" and retrace.end_price <= origin:
                break
            if direction == "down" and retrace.end_price >= origin:
                break
            # 推动笔创出新极值 → 延伸；否则结束
            if direction == "up" and push.end_price > seg_extreme:
                seg_extreme = push.end_price
                end = j
                j += 2
            elif direction == "down" and push.end_price < seg_extreme:
                seg_extreme = push.end_price
                end = j
                j += 2
            else:
                break

        segments.append(Segment(direction=direction, strokes=list(strokes[i:end + 1])))
        i = end + 1

    return segments
