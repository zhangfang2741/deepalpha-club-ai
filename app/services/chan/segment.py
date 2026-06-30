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
    """从笔序列识别线段。

    算法（特征序列简化版）：
    - 线段至少由3笔构成（方向：奇数笔与线段同向，偶数笔为回调）
    - 上升线段：笔1(上)→笔2(下)→笔3(上)，且笔3终点 > 笔1终点（确认新高）
    - 下降线段：笔1(下)→笔2(上)→笔3(下)，且笔3终点 < 笔1终点（确认新低）
    - 线段延伸：若后续同向笔继续创新高/新低，则线段延伸
    - 线段结束：若出现逆向3笔且破坏了本线段的起点，或特征序列出现分型
    """
    if len(strokes) < 3:
        return []

    segments: list[Segment] = []
    i = 0

    while i < len(strokes) - 2:
        s0, s1, s2 = strokes[i], strokes[i + 1], strokes[i + 2]

        # 检查方向是否满足：s0和s2同向，s1反向
        if s0.direction != s2.direction or s0.direction == s1.direction:
            i += 1
            continue

        direction = s0.direction

        if direction == "up":
            # 上升线段：s2终点（顶）必须高于s0终点
            if s2.end_price <= s0.end_price:
                i += 1
                continue
            seg = Segment(direction="up", strokes=[s0, s1, s2])
        else:
            # 下降线段：s2终点（底）必须低于s0终点
            if s2.end_price >= s0.end_price:
                i += 1
                continue
            seg = Segment(direction="down", strokes=[s0, s1, s2])

        # 线段延伸：从第5笔（i+4）开始，每次跳2看同向笔
        # j 指向同向笔，j-1 指向其前的回调笔
        j = i + 4
        while j < len(strokes):
            next_main = strokes[j]
            retrace = strokes[j - 1]

            if next_main.direction != direction:
                break

            if direction == "up" and next_main.end_price > seg.end_price:
                if retrace not in seg.strokes:
                    seg.strokes.append(retrace)
                seg.strokes.append(next_main)
                j += 2
            elif direction == "down" and next_main.end_price < seg.end_price:
                if retrace not in seg.strokes:
                    seg.strokes.append(retrace)
                seg.strokes.append(next_main)
                j += 2
            else:
                break

        segments.append(seg)
        # 从线段最后一笔的下一笔继续搜索
        i = strokes.index(seg.strokes[-1]) + 1

    return segments
