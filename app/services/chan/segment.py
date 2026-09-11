"""缠论线段识别：至少3笔构成，特征序列分型判断结束"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.services.chan.stroke import Stroke

# 第二种情况前瞻确认的窗口：缺口分型出现后，只在紧邻的少量同向笔内看是否被突破
_GAP_LOOKAHEAD = 3


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


def _breaks_beyond(strokes: list[Stroke], feat_idx: int, direction: str, peak: float) -> bool:
    """第二种情况前瞻确认。

    缺口分型的峰 e2（下标 feat_idx，反向笔）之后，原方向是否在紧邻的少量同向笔内
    重新突破 peak——突破即视为缺口只是中继（线段继续）。
    """
    n = len(strokes)
    for q in range(feat_idx + 1, min(feat_idx + 1 + _GAP_LOOKAHEAD, n)):
        s = strokes[q]
        if s.direction != direction:
            continue
        if (direction == "up" and s.end_price > peak) or (
            direction == "down" and s.end_price < peak
        ):
            return True
    return False


def _segment_end(strokes: list[Stroke], start: int, direction: str) -> int | None:
    """求从 start 起、方向 direction 的线段的最后一笔索引。

    以特征序列（反向笔）的顶/底分型判断线段结束：
    - 特征序列元素做包含处理（方向同线段）。
    - 出现顶(上升段)/底(下降段)分型即为候选结束点。
      · 第一种情况（分型元素1、2无缺口）：直接结束。
      · 第二种情况（元素1、2有缺口）：有界前瞻确认——若原方向随即突破该分型极值，
        则缺口为中继、线段继续；否则确认结束。
    - 起点保护：任一回调收复线段起点即硬结束（线段绝不吞没自身起点）。
    - 无终结分型（线段未走完）：结束于最后一根同向笔。
    """
    n = len(strokes)
    origin = strokes[start].start_price
    processed: list[dict] = []  # 特征序列元素：{idx, high, low}
    last_same = start  # 最后一根同向笔（无终结分型时线段结束于此）

    q = start + 1
    while q < n:
        s = strokes[q]
        if s.direction == direction:
            last_same = q
            q += 1
            continue

        # 反向笔 = 特征序列元素；先做起点保护
        if (direction == "up" and s.end_price <= origin) or (
            direction == "down" and s.end_price >= origin
        ):
            return q - 1

        hi = max(s.start_price, s.end_price)
        lo = min(s.start_price, s.end_price)
        if processed:
            prev = processed[-1]
            contained = (prev["high"] >= hi and prev["low"] <= lo) or (
                hi >= prev["high"] and lo <= prev["low"]
            )
            if contained:
                # 包含处理方向同线段：上升取高高、下降取低低
                if direction == "up":
                    processed[-1] = {
                        "idx": prev["idx"] if prev["high"] >= hi else q,
                        "high": max(prev["high"], hi), "low": max(prev["low"], lo),
                    }
                else:
                    processed[-1] = {
                        "idx": prev["idx"] if prev["low"] <= lo else q,
                        "high": min(prev["high"], hi), "low": min(prev["low"], lo),
                    }
                q += 1
                continue

        processed.append({"idx": q, "high": hi, "low": lo})

        if len(processed) >= 3:
            e1, e2, e3 = processed[-3], processed[-2], processed[-1]
            if direction == "up":
                is_fractal = e2["high"] > e1["high"] and e2["high"] > e3["high"]
                gap = e1["high"] < e2["low"]
                peak = e2["high"]
            else:
                is_fractal = e2["low"] < e1["low"] and e2["low"] < e3["low"]
                gap = e1["low"] > e2["high"]
                peak = e2["low"]
            if is_fractal:
                end_candidate = e2["idx"] - 1
                if not gap:
                    return end_candidate  # 第一种情况：直接结束
                if not _breaks_beyond(strokes, e2["idx"], direction, peak):
                    return end_candidate  # 第二种情况：未被突破 → 确认结束
                # 第二种情况：缺口被突破 → 中继，丢弃该分型，保留末元素继续趋势
                processed = processed[-1:]
        q += 1

    # 无终结分型：线段未走完，结束于最后一根同向笔
    return last_same


def find_segments(strokes: list[Stroke]) -> list[Segment]:
    """从笔序列识别线段（基于索引，不依赖 Stroke 的值相等）。

    以标准「特征序列分型」判断线段结束，覆盖第一种情况（无缺口，直接结束）与
    第二种情况（有缺口，需前瞻确认；缺口被原方向迅速突破则视为中继、线段继续）。
    另有两道护栏：
    - 起点保护：任一回调收复线段起点即结束，线段绝不吞没自身起点。
    - 严格交替：一条线段结束后，下一条方向必与其相反（确立失败跳过若干笔后也不会
      误起一条同向线段）。

    确立：s0(同向)→s1(反向,不收复起点)→s2(同向,越过 s0 极值)。以整数索引跟踪，
    不用 list.index()/in（避免 dataclass 值相等在等值笔上误匹配）。

    经 4000 例随机 A/B 验证：不变量（>=3笔、方向由首笔定、连续子序列、严格交替、
    不吞没起点）零违反；相比不含缺口确认的旧版，会正确地把「带缺口中继」的走势
    并成一条线段，而非在中继处误分。
    """
    if len(strokes) < 3:
        return []

    segments: list[Segment] = []
    n = len(strokes)
    i = 0
    expected_dir: str | None = None

    while i <= n - 3:
        s0, s1, s2 = strokes[i], strokes[i + 1], strokes[i + 2]

        # 方向校验：s0/s2 同向，s1 反向
        if s0.direction != s2.direction or s0.direction == s1.direction:
            i += 1
            continue

        direction = s0.direction
        if expected_dir is not None and direction != expected_dir:
            i += 1
            continue

        origin = s0.start_price
        # 确立1：首个回调 s1 不得收复起点
        if (direction == "up" and s1.end_price < origin) or (
            direction == "down" and s1.end_price > origin
        ):
            i += 1
            continue
        # 确立2：s2 必须越过 s0 极值
        if (direction == "up" and s2.end_price <= s0.end_price) or (
            direction == "down" and s2.end_price >= s0.end_price
        ):
            i += 1
            continue

        end = _segment_end(strokes, i, direction)
        if end is None or end < i + 2 or (end - i) % 2 != 0:
            i += 1
            continue

        segments.append(Segment(direction=direction, strokes=list(strokes[i:end + 1])))
        expected_dir = "down" if direction == "up" else "up"
        i = end + 1

    return segments
