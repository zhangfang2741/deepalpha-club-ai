"""缠论分型（fractal）与包含关系处理单元测试。

不变量：
1. 合并K线序列相邻不含包含关系。
2. 返回的每个分型都满足顶/底的局部定义（在合并K线上成立）。
3. 分型按合并K线索引升序返回，不做非标准的价格贪心丢弃。
"""
from __future__ import annotations

from app.services.chan.fractal import find_fractals, merge_candles


def _bar(t: int, o: float, h: float, low: float, c: float) -> dict:
    return {"time": f"D{t:03d}", "open": o, "high": h, "low": low, "close": c, "volume": 1000}


def test_merge_removes_containment():
    # 第二根被第一根包含，应合并为一根
    bars = [_bar(0, 10, 20, 8, 15), _bar(1, 14, 18, 12, 16), _bar(2, 16, 25, 15, 22)]
    merged = merge_candles(bars)
    # 相邻合并K线之间不应再有包含关系
    for a, b in zip(merged, merged[1:], strict=False):
        a_contains_b = a.high >= b.high and a.low <= b.low
        b_contains_a = b.high >= a.high and b.low <= a.low
        assert not (a_contains_b or b_contains_a)


def test_fractals_are_valid_and_ordered():
    # 明确的 上-下-上 折线
    pivots = [100, 120, 105, 130, 110, 140]
    bars: list[dict] = []
    t = 0
    prev = pivots[0]
    for tgt in pivots[1:]:
        for s in range(1, 7):
            o = prev + (tgt - prev) * (s - 1) / 6
            c = prev + (tgt - prev) * s / 6
            bars.append(_bar(t, round(o, 2), round(max(o, c) + 0.5, 2),
                             round(min(o, c) - 0.5, 2), round(c, 2)))
            t += 1
        prev = tgt
    merged = merge_candles(bars)
    fractals = find_fractals(merged)
    assert fractals
    # 升序
    idxs = [f.idx for f in fractals]
    assert idxs == sorted(idxs)
    # 每个分型在合并K线上确实是局部顶/底
    for f in fractals:
        i = f.idx
        left, mid, right = merged[i - 1], merged[i], merged[i + 1]
        if f.type == "top":
            assert mid.high > left.high and mid.high > right.high
        else:
            assert mid.low < left.low and mid.low < right.low


def test_too_few_candles():
    assert find_fractals([]) == []
    bars = [_bar(0, 10, 12, 9, 11), _bar(1, 11, 13, 10, 12)]
    assert find_fractals(merge_candles(bars)) == []
