"""缠论线段（segment）识别单元测试。

不变量：
1. 线段至少由3笔构成，方向由第一笔决定，内部笔为该段的连续子序列。
2. 线段不得吞没「收复其起点」的反向走势（下降线段不能包含创出新高的一段）。
3. 识别使用索引而非 dataclass 值相等，避免同值笔互相误匹配。
"""
from __future__ import annotations

from app.services.chan.fractal import Fractal, MergedCandle
from app.services.chan.segment import find_segments
from app.services.chan.stroke import Stroke


def _mc(idx: int, high: float, low: float) -> MergedCandle:
    return MergedCandle(idx=idx, time=f"D{idx:03d}", open=(high + low) / 2, high=high,
                        low=low, close=(high + low) / 2, raw_start=idx, raw_end=idx)


def _fx(kind: str, idx: int, price: float) -> Fractal:
    # Fractal.price 顶取 candle.high、底取 candle.low，构造时让其正好等于 price
    if kind == "top":
        mid = _mc(idx, high=price, low=price - 1)
    else:
        mid = _mc(idx, high=price + 1, low=price)
    return Fractal(type=kind, candle=mid, left=_mc(idx - 1, price, price - 2),
                   right=_mc(idx + 1, price, price - 2))


def _stroke(direction: str, idx: int, start_price: float, end_price: float) -> Stroke:
    start_kind = "bottom" if direction == "up" else "top"
    end_kind = "top" if direction == "up" else "bottom"
    return Stroke(
        direction=direction,
        start=_fx(start_kind, idx * 10, start_price),
        end=_fx(end_kind, idx * 10 + 5, end_price),
    )


def _chain(prices: list[float]) -> list[Stroke]:
    """由一串转折价构造首尾相连、方向交替的笔序列。"""
    strokes: list[Stroke] = []
    for i in range(len(prices) - 1):
        direction = "up" if prices[i + 1] > prices[i] else "down"
        strokes.append(_stroke(direction, i, prices[i], prices[i + 1]))
    return strokes


def test_up_segment_three_strokes():
    # 100->130->115->140：一条上升线段（3笔）
    strokes = _chain([100, 130, 115, 140])
    segs = find_segments(strokes)
    assert len(segs) == 1
    assert segs[0].direction == "up"
    assert segs[0].stroke_count == 3
    assert segs[0].start_price == 100
    assert segs[0].end_price == 140


def test_segment_not_swallow_new_high():
    # 130->114->125->109->140->119：
    # 前3笔构成下降线段(130->109)，随后 109->140 收复并突破起点130，
    # 下降线段必须结束，不能把创出新高(140>130)的一段吞进来。
    strokes = _chain([130, 114, 125, 109, 140, 119])
    segs = find_segments(strokes)
    assert segs, "应至少识别出一条下降线段"
    down = segs[0]
    assert down.direction == "down"
    # 该下降线段的最高点不得超过其起点 130（未吞没创新高走势）
    assert down.high <= 130 + 1e-9
    assert down.end_price <= 130


def test_segment_strokes_are_contiguous_subsequence():
    strokes = _chain([100, 130, 115, 140, 120, 150, 130, 160])
    segs = find_segments(strokes)
    assert segs
    for seg in segs:
        # 段内笔在原序列中连续
        first = strokes.index(seg.strokes[0])
        for offset, s in enumerate(seg.strokes):
            assert strokes[first + offset] is s
        assert seg.stroke_count >= 3


def test_too_few_strokes():
    assert find_segments([]) == []
    assert find_segments(_chain([100, 120])) == []  # 仅1笔
