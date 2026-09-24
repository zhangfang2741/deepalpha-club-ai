"""次级别确认（日线定方向 × 30 分钟找买卖点）联动判定测试。"""
from __future__ import annotations

from app.services.chan.analyzer import ChanAnalysisResult, Recommendation
from app.services.chan.fractal import MergedCandle
from app.services.chan.signals import Signal
from app.services.chan.sub_level import build_sub_level


def _daily(bias: str, label: str = "技术面偏强") -> ChanAnalysisResult:
    r = ChanAnalysisResult(symbol="T", bars_count=100)
    r.recommendation = Recommendation(action="watch", action_label=label, bias=bias)
    return r


def _mc(t: str) -> MergedCandle:
    return MergedCandle(idx=0, time=t, open=1, high=2, low=0.5, close=1.5, raw_start=0, raw_end=0)


def _sub(signals: list[tuple[str, str]], days=("2026-09-21", "2026-09-22", "2026-09-23")) -> ChanAnalysisResult:
    """30 分钟结果：每天两根合并K线；signals = [(type, time)]。"""
    r = ChanAnalysisResult(symbol="T", bars_count=50)
    r.merged_candles = [_mc(f"{d} {hm}") for d in days for hm in ("09:30", "15:30")]
    r.strokes = [object()] * 5  # type: ignore[assignment]  # 只用于判断「能成结构」，内容不参与判定
    r.signals = [Signal(type=t, time=tm, price=10.0, strength="medium", divergence=None,  # type: ignore[arg-type]
                        description="") for t, tm in signals]
    return r


def test_bullish_daily_with_recent_30min_buy_is_resonance_buy():
    res = build_sub_level(_daily("bullish"), _sub([("buy1", "2026-09-23 10:00")]))
    assert res.verdict == "resonance_buy"
    assert res.verdict_label == "共振买点"
    assert [s.type for s in res.recent_signals] == ["buy1"]
    assert "技术面偏强" in res.detail


def test_bearish_daily_with_recent_30min_sell_is_resonance_sell():
    res = build_sub_level(_daily("bearish", "技术面偏弱"), _sub([("sell2", "2026-09-22 14:00")]))
    assert res.verdict == "resonance_sell"


def test_opposite_direction_is_counter_trend():
    res = build_sub_level(_daily("bearish", "技术面偏弱"), _sub([("buy1", "2026-09-23 10:00")]))
    assert res.verdict == "counter_trend"
    assert "反弹" in res.detail


def test_signals_older_than_last_two_trading_days_are_ignored():
    res = build_sub_level(_daily("bullish"), _sub([("buy1", "2026-09-21 10:00")]))
    assert res.verdict == "waiting"
    assert res.recent_signals == []


def test_neutral_daily_waits_but_still_lists_recent_signals():
    res = build_sub_level(_daily("neutral", "技术面多空僵持"), _sub([("buy2", "2026-09-23 10:00")]))
    assert res.verdict == "waiting"
    assert [s.type for s in res.recent_signals] == ["buy2"]


def test_latest_recent_signal_decides_when_both_sides_present():
    sub = _sub([("sell1", "2026-09-22 10:00"), ("buy2", "2026-09-23 11:00")])
    res = build_sub_level(_daily("bullish"), sub)
    assert res.verdict == "resonance_buy"


def test_missing_or_unstructured_sub_level_is_unavailable():
    assert build_sub_level(_daily("bullish"), None).verdict == "unavailable"
    empty = _sub([])
    empty.strokes = []
    assert build_sub_level(_daily("bullish"), empty).verdict == "unavailable"


def test_english_labels():
    res = build_sub_level(_daily("bullish", "Technicals firm"), _sub([("buy1", "2026-09-23 10:00")]), lang="en")
    assert res.verdict_label == "Aligned buy"
    assert res.daily_bias == "bullish"
