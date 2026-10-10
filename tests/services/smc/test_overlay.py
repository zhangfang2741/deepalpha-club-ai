"""SMC 图表指标（overlay）：对齐到合并 K 线下标、只留要画的、不带操作措辞。"""
from __future__ import annotations

import json
from dataclasses import asdict

from app.services.smc.overlay import MAX_FVGS, MAX_ORDER_BLOCKS, build_overlay
from tests.services.smc.test_algo import _bars, _line


def _times(bars: list[dict]) -> list[str]:
    return [b["time"] for b in bars]


def _wave_bars(n_waves: int = 8) -> list[dict]:
    knots = [10.0]
    for k in range(n_waves):
        knots += [knots[-1] + 12 + k, knots[-1] + 12 + k - 7]
    return _bars(_line(*knots))


def test_overlay_aligns_everything_to_candle_index():
    bars = _wave_bars()
    o = build_overlay(bars, _times(bars), "daily", swing_len=3)
    assert o is not None and o.breaks
    n = len(bars)
    for b in o.breaks:
        assert 0 <= b.level_idx <= b.break_idx < n
        assert bars[b.break_idx]["time"] == b.time
    for ob in o.order_blocks:
        assert ob.idx <= ob.end_idx <= n - 1
    assert o.trend in ("bull", "bear", "none")


def test_overlay_maps_to_merged_candle_containing_the_bar():
    bars = _wave_bars()
    end_times = [bars[i]["time"] for i in range(1, len(bars), 2)]   # 每两根并成一根
    o = build_overlay(bars, end_times, "daily", swing_len=3)
    assert o is not None
    for b in o.breaks:
        assert end_times[b.break_idx] >= b.time
        assert b.break_idx == 0 or end_times[b.break_idx - 1] < b.time


def test_overlay_only_keeps_unmitigated_blocks_and_open_gaps():
    bars = _wave_bars(12)
    o = build_overlay(bars, _times(bars), "daily", swing_len=3)
    assert o is not None
    assert all(not ob.mitigated for ob in o.order_blocks)
    assert len(o.order_blocks) <= MAX_ORDER_BLOCKS and len(o.fvgs) <= MAX_FVGS
    # 未失效的区块一直画到最后一根
    assert all(ob.end_idx == len(bars) - 1 for ob in o.order_blocks)


def test_overlay_drops_breaks_before_visible_from():
    bars = _wave_bars()
    cut = bars[len(bars) // 2]["time"]
    full = build_overlay(bars, _times(bars), "daily", swing_len=3)
    part = build_overlay(bars, _times(bars), "daily", swing_len=3, visible_from=cut)
    assert part is not None and full is not None
    assert part.breaks and len(part.breaks) < len(full.breaks)
    assert all(b.time >= cut for b in part.breaks)


def test_overlay_none_when_too_few_bars():
    bars = _bars([10.0] * 5)
    assert build_overlay(bars, _times(bars), "daily") is None
    assert build_overlay([], [], "daily") is None


def test_overlay_has_no_trading_wording():
    """App 只陈列事实：序列化出来的所有文字（代码 / 标签）都不能带买卖导向词。"""
    bars = _wave_bars(10)
    o = build_overlay(bars, _times(bars), "daily", swing_len=3)
    text = json.dumps(asdict(o), ensure_ascii=False)
    for w in ("买入", "卖出", "做多", "做空", "入场", "离场", "止损", "止盈", "建议", "目标价"):
        assert w not in text
