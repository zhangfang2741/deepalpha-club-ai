"""威科夫图表指标（overlay）：对齐到合并 K 线下标、不带操作措辞。"""
from __future__ import annotations

from app.services.wyckoff.overlay import build_overlay
from tests.services.wyckoff.test_analyzer import _make_accumulation_bars


def _times(bars: list[dict]) -> list[str]:
    return [b["time"] for b in bars]


def test_overlay_aligns_events_and_range_to_candle_index():
    bars = _make_accumulation_bars()
    o = build_overlay("TEST", bars, _times(bars))
    assert o is not None and o.trading_range is not None
    assert o.stage == "markup" or o.context == "accumulation"
    codes = {e.code for e in o.events}
    assert {"SC", "AR"} <= codes
    for e in o.events:
        # 合并 K 线与原始 K 线一一对应时，下标就是原始下标
        assert bars[e.idx]["time"] == e.time
        assert e.side in ("high", "low")
    assert o.trading_range.start_idx <= o.trading_range.end_idx == len(bars) - 1
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
