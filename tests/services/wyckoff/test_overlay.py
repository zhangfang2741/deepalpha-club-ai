"""威科夫图表指标（overlay）：对齐到合并 K 线下标、不带操作措辞。"""
from __future__ import annotations

from app.services.wyckoff.overlay import build_overlay
from tests.services.wyckoff.test_analyzer import _make_accumulation_bars


def _times(bars: list[dict]) -> list[str]:
    return [b["time"] for b in bars]


def test_overlay_aligns_events_and_range_to_candle_index():
    bars = _make_accumulation_bars()
    o = build_overlay("TEST", bars, _times(bars))
    assert o is not None and o.ranges
    assert o.stage == "markup" or o.context == "accumulation"
    codes = {e.code for e in o.events}
    assert {"SC", "AR"} <= codes
    for e in o.events:
        # 合并 K 线与原始 K 线一一对应时，下标就是原始下标
        assert bars[e.idx]["time"] == e.time
        assert e.side in ("high", "low")
    r0 = o.ranges[0]
    assert r0.start_idx <= r0.end_idx <= len(bars) - 1
    sc = next(e for e in o.events if e.code == "SC")
    assert sc.side == "low"


def test_overlay_maps_to_merged_candle_containing_the_bar():
    """合并 K 线把几根原始 K 线并成一根时，事件落在「包含它的那一根」上。"""
    bars = _make_accumulation_bars()
    # 每两根并成一根：end_time 取第二根
    end_times = [bars[i]["time"] for i in range(1, len(bars), 2)]
    o = build_overlay("TEST", bars, end_times)
    assert o is not None
    for e in o.events:
        assert end_times[e.idx] >= e.time
        assert e.idx == 0 or end_times[e.idx - 1] < e.time


def test_overlay_only_uses_visible_window():
    bars = _make_accumulation_bars()
    o = build_overlay("TEST", bars, _times(bars), visible_from=bars[-5]["time"])
    assert o is None  # 只剩 5 根，不够分析


def test_overlay_none_without_volume_or_candles():
    bars = [dict(b, volume=0) for b in _make_accumulation_bars()]
    assert build_overlay("TEST", bars, _times(bars)) is None
    assert build_overlay("TEST", _make_accumulation_bars(), []) is None


def test_overlay_has_no_trading_wording():
    """图上只陈列结构事实：字段里不出现买卖 / 操作措辞。"""
    import dataclasses
    import json
    bars = _make_accumulation_bars()
    o = build_overlay("TEST", bars, _times(bars))
    text = json.dumps(dataclasses.asdict(o), ensure_ascii=False)
    for w in ("买点", "卖点", "低吸", "减仓", "离场", "做空", "建议"):
        assert w not in text


def test_overlay_range_and_events_stop_at_breakout():
    """价格收盘离开区间后，区间带与事件都只到突破那根（之后的放量是趋势，不是区间结构）。"""
    bars = _make_accumulation_bars()
    o = build_overlay("TEST", bars, _times(bars))
    assert o is not None and o.ranges
    r = o.ranges[0]
    # 夹具末尾是连续放量上冲出区间：区间不该一直画到最后一根
    assert o.breakout == "up"
    assert r.end_idx < len(bars) - 1
    assert all(e.idx <= r.end_idx for e in o.events)
    assert bars[r.end_idx]["close"] > r.resistance


def test_overlay_degenerate_range_is_undetermined():
    """区间宽度不到支撑价 4% 时按结构不明处理：不画带、不标事件、阶段也不保留。"""
    from app.services.wyckoff import overlay as mod
    from app.services.wyckoff.analyzer import WyckoffAnalyzer

    bars = _make_accumulation_bars()
    r = WyckoffAnalyzer().analyze("TEST", bars)
    assert r.trading_range is not None
    wide = r.trading_range.width / r.trading_range.support
    assert wide > mod.MIN_RANGE_WIDTH  # 夹具本身是宽区间

    old = mod.MIN_RANGE_WIDTH
    try:
        mod.MIN_RANGE_WIDTH = wide + 0.01  # 抬高门槛 → 夹具的区间变成「太窄」
        o = build_overlay("TEST", bars, _times(bars))
    finally:
        mod.MIN_RANGE_WIDTH = old
    assert o is not None
    assert o.ranges == [] and o.events == []
    assert o.stage == "undetermined" and o.context == "undetermined"


def test_overlay_rolls_to_next_structure_after_breakout():
    """价格离开区间后从突破处再识别一段：两段走势 → 两段区间，按时间先后、不重叠。"""
    first = _make_accumulation_bars()
    second = [dict(b, time=b["time"].replace("2024-01", "2024-02")) for b in first]
    bars = first + second
    o = build_overlay("TEST", bars, _times(bars))
    assert o is not None
    assert len(o.ranges) >= 2
    for a, b in zip(o.ranges, o.ranges[1:]):
        assert a.start_idx < b.start_idx and a.end_idx <= b.end_idx
    # 事件都落在某一段区间的时间范围内（突破之后不再标）
    for e in o.events:
        assert any(r.start_idx - 8 <= e.idx <= r.end_idx for r in o.ranges), e
