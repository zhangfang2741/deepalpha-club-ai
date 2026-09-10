"""缠论笔（stroke）识别单元测试。

核心不变量（缠论标准 + 画图连续性）：
1. 相邻两笔必须首尾相连：前一笔终点即后一笔起点（否则图上断裂）。
2. 笔方向严格交替（上升笔↔下降笔）。
3. 成笔两端一顶一底，且满足最小合并K线间隔。
4. 同型分型只保留极值一端；若极值发生在已成笔之后，应延伸该笔端点而非留下缺口。
"""
from __future__ import annotations

from app.services.chan.fractal import Fractal, MergedCandle
from app.services.chan.stroke import find_strokes


def _mc(idx: int, high: float, low: float) -> MergedCandle:
    return MergedCandle(
        idx=idx, time=f"D{idx:03d}", open=(high + low) / 2, high=high, low=low,
        close=(high + low) / 2, raw_start=idx, raw_end=idx,
    )


def _fx(kind: str, idx: int, price: float) -> Fractal:
    """构造一个位于 idx 的顶/底分型（左右邻用占位K线，价格不影响笔逻辑）。"""
    if kind == "top":
        mid = _mc(idx, high=price, low=price - 1)
    else:
        mid = _mc(idx, high=price + 1, low=price)
    return Fractal(type=kind, candle=mid, left=_mc(idx - 1, price, price - 2),
                   right=_mc(idx + 1, price, price - 2))


def _assert_connected_alternating(strokes) -> None:
    for a, b in zip(strokes, strokes[1:], strict=False):
        assert a.end is b.start, "相邻笔必须首尾相连（前一笔终点=后一笔起点）"
        assert a.direction != b.direction, "相邻笔方向必须交替"


def test_basic_alternating_strokes_connected():
    fractals = [
        _fx("bottom", 0, 10.0),
        _fx("top", 5, 20.0),
        _fx("bottom", 10, 12.0),
        _fx("top", 15, 25.0),
    ]
    strokes = find_strokes(fractals)
    assert len(strokes) == 3
    assert [s.direction for s in strokes] == ["up", "down", "up"]
    _assert_connected_alternating(strokes)


def test_min_gap_rejects_close_fractals():
    # 顶底间隔不足 min_gap（默认4），不成笔
    fractals = [_fx("bottom", 0, 10.0), _fx("top", 2, 20.0)]
    assert find_strokes(fractals) == []
    # 间隔足够则成笔
    fractals2 = [_fx("bottom", 0, 10.0), _fx("top", 4, 20.0)]
    assert len(find_strokes(fractals2)) == 1


def test_same_type_keeps_extreme_before_stroke():
    # 起点侧连续两个底，取更低的底作为上升笔起点
    fractals = [
        _fx("bottom", 0, 12.0),
        _fx("bottom", 3, 9.0),   # 更低的底
        _fx("top", 8, 20.0),
    ]
    strokes = find_strokes(fractals)
    assert len(strokes) == 1
    assert strokes[0].direction == "up"
    assert strokes[0].start_price == 9.0  # 取更低的底


def test_extreme_after_stroke_extends_endpoint_no_gap():
    # 上升笔成立后，又出现更高的顶（且中间无有效底）：应延伸该笔终点，保持连续
    fractals = [
        _fx("bottom", 0, 10.0),
        _fx("top", 5, 20.0),     # 先成上升笔 10->20
        _fx("top", 9, 26.0),     # 更高的顶，延伸终点到 26
        _fx("bottom", 14, 15.0),
    ]
    strokes = find_strokes(fractals)
    _assert_connected_alternating(strokes)
    assert strokes[0].direction == "up"
    assert strokes[0].end_price == 26.0, "更高的顶应延伸上升笔终点"
    assert strokes[1].start_price == 26.0, "下降笔应从延伸后的顶开始，图上不断裂"


def test_empty_and_single():
    assert find_strokes([]) == []
    assert find_strokes([_fx("bottom", 0, 10.0)]) == []
