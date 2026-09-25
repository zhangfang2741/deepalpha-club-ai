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
    # 是否已由特征序列分型 / 收复起点终结；False = 数据走到尽头、线段仍在进行（终点暂取当前极值）
    terminated: bool = True

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

    # 线段力度：由所含笔汇总，口径与笔一致（价差取两端价差，量能/时长为各笔之和）
    @property
    def power_price(self) -> float:
        return round(abs(self.end_price - self.start_price), 2)

    @property
    def power_volume(self) -> float:
        return sum(s.power_volume for s in self.strokes)

    @property
    def length(self) -> int:
        return sum(s.length for s in self.strokes)


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


_PRICE_REL_TOL = 1e-6  # 价格比较的相对容差


def _extreme_end(strokes: list[Stroke], start: int, last: int, direction: str) -> int:
    """[start, last] 内同向笔中终点最极端的一笔（并列取靠后者）——线段终点必须是极值点。"""
    best = start
    for k in range(start, last + 1, 2):
        e, b = strokes[k].end_price, strokes[best].end_price
        if (direction == "up" and e >= b) or (direction == "down" and e <= b):
            best = k
    return best


def _extreme_on_first(strokes: list[Stroke], start: int, end: int, direction: str) -> bool:
    """线段首笔之后是否再没有严格创出新极值（持平不算）。

    此时只是「一笔 + 其后横盘」，构不成线段（特征序列分型的第一元素须在极值之前，这里不存在，终点也落不到极值上）。
    """
    first = strokes[start].end_price
    tol = abs(first) * _PRICE_REL_TOL  # 前复权价有浮点尾差，差几个 1e-6 的「新高」视为持平
    return not any(
        strokes[k].end_price > first + tol if direction == "up" else strokes[k].end_price < first - tol
        for k in range(start + 2, end + 1, 2)
    )


def _segment_scan(
    strokes: list[Stroke], start: int, direction: str, feat_from: int | None = None
) -> tuple[int | None, bool]:
    """求从 start 起、方向 direction 的线段的最后一笔索引。

    以特征序列（反向笔）的顶/底分型判断线段结束：
    - 特征序列元素做包含处理（方向同线段）。
    - 出现顶(上升段)/底(下降段)分型即为候选结束点。
      · 第一种情况（分型元素1、2无缺口）：直接结束。
      · 第二种情况（元素1、2有缺口）：有界前瞻确认——若原方向随即突破该分型极值，
        则缺口为中继、线段继续；否则确认结束。
    - 起点保护：任一回调收复线段起点即硬结束（线段绝不吞没自身起点）。
    - 无终结分型（线段未走完）：结束于最后一根同向笔。

    feat_from：线段被延续（新极值）后从此处重建特征序列；新极值之前的特征元素
    已被突破，不再参与终结分型判断。
    """
    n = len(strokes)
    origin = strokes[start].start_price
    processed: list[dict] = []  # 特征序列元素：{idx, high, low}
    q = start + 1 if feat_from is None else feat_from
    last_same = q - 1  # 最后一根同向笔（无终结分型时线段结束于此）

    while q < n:
        s = strokes[q]
        if s.direction == direction:
            last_same = q
            q += 1
            continue

        # 反向笔 = 特征序列元素；先做起点保护：线段被破坏，结束于段内极值笔
        if (direction == "up" and s.end_price <= origin) or (
            direction == "down" and s.end_price >= origin
        ):
            return _extreme_end(strokes, start, q - 1, direction), True

        hi = max(s.start_price, s.end_price)
        lo = min(s.start_price, s.end_price)
        if processed:
            prev = processed[-1]
            contained = (prev["high"] >= hi and prev["low"] <= lo) or (
                hi >= prev["high"] and lo <= prev["low"]
            )
            # 分型第一、第二元素之间不做包含处理：新元素起于线段新极值（上升段更高的高点
            # / 下降段更低的低点）时它是潜在的分型顶/底，独立保留，否则极值会被并掉、
            # 线段终点落不到极值上。
            new_extreme = hi > prev["high"] if direction == "up" else lo < prev["low"]
            if contained and not new_extreme:
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
                    return end_candidate, True  # 第一种情况：直接结束
                if not _breaks_beyond(strokes, e2["idx"], direction, peak):
                    return end_candidate, True  # 第二种情况：未被突破 → 确认结束
                # 第二种情况：缺口被突破 → 中继，丢弃该分型，保留末元素继续趋势
                processed = processed[-1:]
        q += 1

    # 无终结分型：线段未走完（数据到头），终点暂取当前极值、标记未终结——
    # 画到最后一根同向笔会停在半路的非极值处，看起来像已结束
    return _extreme_end(strokes, start, last_same, direction), False


def _segment_end(
    strokes: list[Stroke], start: int, direction: str, feat_from: int | None = None
) -> int | None:
    """_segment_scan 的终点部分（不关心是否终结的调用方用）。"""
    return _segment_scan(strokes, start, direction, feat_from)[0]


def find_segments(strokes: list[Stroke]) -> list[Segment]:
    """从笔序列识别线段（基于索引，不依赖 Stroke 的值相等）。

    以标准「特征序列分型」判断线段结束，覆盖第一种情况（无缺口，直接结束）与
    第二种情况（有缺口，需前瞻确认；缺口被原方向迅速突破则视为中继、线段继续）。

    首尾相接：第一条线段按确立规则找起点——s0(同向)→s1(反向,不收复起点)→s2(同向)，
    且线段极值不能落在首笔（否则只是「一笔 + 横盘」）；此后每条线段都从前一段终点
    直接开始，同样三笔重叠即成段、极值不在首笔。新线段起步即被原方向突破前段极值（首个回调收复自身
    起点）说明前段并未结束：从断点起重建特征序列、延续前段到新的终点。
    线段被破坏（回调收复起点）时终点取段内极值笔，而非触发前一笔。
    只有「回调已收复前段起点又被立即突破」的极端形态无法延续，才退回确立规则
    跳过若干笔（此时会留下空档）。

    护栏：起点保护（线段绝不吞没自身起点）、首尾相接的线段方向必然交替。
    以整数索引跟踪，不用 list.index()/in（避免 dataclass 值相等在等值笔上误匹配）。
    """
    if len(strokes) < 3:
        return []

    segments: list[Segment] = []
    starts: list[int] = []  # 各线段首笔下标
    n = len(strokes)
    i = 0
    expected_dir: str | None = None
    chained = False  # i 是否紧接前一段终点（可直接起新段）

    while i <= n - 3:
        if chained:
            direction = strokes[i].direction
            end, term = _segment_scan(strokes, i, direction)
            if end is not None and end >= i + 2 and not _extreme_on_first(strokes, i, end, direction):
                segments.append(Segment(direction=direction, strokes=list(strokes[i:end + 1]), terminated=term))
                starts.append(i)
                expected_dir = "down" if direction == "up" else "up"
                i = end + 1
                continue
            # 新段不足三笔即被破坏（其极值就是首笔、随后被收复起点 = 前段终点）：
            # 前段创出新极值、并未结束——从断点起重建特征序列，延续前段
            prev_start, prev = starts[-1], segments[-1]
            end, term = _segment_scan(strokes, prev_start, prev.direction, feat_from=i)
            new_high = end is not None and end > i - 1 and (
                strokes[end].end_price > prev.end_price if prev.direction == "up"
                else strokes[end].end_price < prev.end_price)
            if new_high and end is not None:
                segments[-1] = Segment(direction=prev.direction, strokes=list(strokes[prev_start:end + 1]),
                                       terminated=term)
                i = end + 1
                continue
            # 前段尚未终结（数据到头、终点暂取当前极值）：之后这几笔是它还没走完的部分，
            # 不另起同向线段，尾部留给后续走势确认
            if not prev.terminated:
                break
            # 失败的反转：前段刚成形就被一笔收复起点并创出反向新极值——前段是失败的反转，
            # 再往前那条同向线段并未结束。撤掉前段、从它的起点重建特征序列延续更早那段，
            # 终点仍由特征序列分型确认、落在极值上。
            if len(segments) >= 2 and segments[-2].direction == strokes[i].direction \
                    and starts[-2] + segments[-2].stroke_count == prev_start:
                older_start, older = starts[-2], segments[-2]
                end, term = _segment_scan(strokes, older_start, older.direction, feat_from=prev_start)
                extends = end is not None and end >= i and (
                    strokes[end].end_price < older.end_price if older.direction == "down"
                    else strokes[end].end_price > older.end_price)
                if extends and end is not None:
                    segments.pop()
                    starts.pop()
                    segments[-1] = Segment(direction=older.direction,
                                           strokes=list(strokes[older_start:end + 1]), terminated=term)
                    expected_dir = "down" if older.direction == "up" else "up"
                    i = end + 1
                    continue
            # 前段也无法延续（回调已收复前段起点）：退回确立规则。中间这一两笔构不成
            # 线段、本身就是反向运动，之后的线段按实际走势定方向，不强求与前段交替。
            chained = False
            expected_dir = None

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
        end, term = _segment_scan(strokes, i, direction)
        if end is None or end < i + 2 or (end - i) % 2 != 0 or _extreme_on_first(strokes, i, end, direction):
            i += 1
            continue

        segments.append(Segment(direction=direction, strokes=list(strokes[i:end + 1]), terminated=term))
        starts.append(i)
        expected_dir = "down" if direction == "up" else "up"
        i = end + 1
        chained = True

    return segments
