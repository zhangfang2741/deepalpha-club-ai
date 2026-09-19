"""信号雷达纯聚合逻辑单测（无 IO）。"""
from __future__ import annotations

from app.services.chan.analyzer import ChanAnalysisResult, Recommendation
from app.services.chan.signals import Signal
from app.services.signal_radar.service import (
    RawSignal,
    aggregate_days,
    build_raw_signal,
    strength_from_score,
)


def _sig(sig_type: str, time: str, price: float, strength: str = "medium") -> Signal:
    return Signal(
        type=sig_type, time=time, price=price, strength=strength,
        divergence=None, description="", confirmed=True, lang="zh",
    )


def _raw(symbol: str, day: str, side: str, strength: float) -> RawSignal:
    return RawSignal(
        symbol=symbol, name=symbol, side=side, label="一买" if side == "buy" else "一卖",
        signal_type="buy1" if side == "buy" else "sell1", date=day, price=10.0,
        strength=strength, bias="bullish" if side == "buy" else "bearish",
        signal_strength="medium", confirmed=True,
    )


class TestStrengthFromScore:
    def test_zero(self):
        assert strength_from_score(0.0) == 0.0

    def test_saturates_at_one(self):
        assert strength_from_score(99.0) == 1.0

    def test_sign_independent(self):
        assert strength_from_score(-3.0) == strength_from_score(3.0)

    def test_monotonic(self):
        assert strength_from_score(1.0) < strength_from_score(4.0)


class TestBuildRawSignal:
    def test_none_when_no_signal(self):
        r = ChanAnalysisResult(symbol="X", bars_count=100)
        assert build_raw_signal("X", "测试", r) is None

    def test_uses_recommendation_score_for_strength(self):
        sig = _sig("buy1", "2026-09-19", 12.34)
        r = ChanAnalysisResult(symbol="X", bars_count=100, signals=[sig], latest_signal=sig)
        r.recommendation = Recommendation(
            action="buy", action_label="技术面偏强", bias="bullish", score=4.0,
        )
        raw = build_raw_signal("NVDA", "英伟达", r)
        assert raw is not None
        assert raw.side == "buy"
        assert raw.name == "英伟达"
        assert raw.date == "2026-09-19"
        assert raw.bias == "bullish"
        assert raw.strength == strength_from_score(4.0)

    def test_fallback_strength_without_recommendation(self):
        sig = _sig("sell1", "2026-09-18", 50.0, strength="strong")
        r = ChanAnalysisResult(symbol="X", bars_count=100, signals=[sig], latest_signal=sig)
        raw = build_raw_signal("AAPL", "苹果", r)
        assert raw is not None
        assert raw.side == "sell"
        assert raw.bias == "bearish"
        assert 0.0 < raw.strength <= 1.0

    def test_date_is_truncated_to_day(self):
        sig = _sig("buy1", "2026-09-19T00:00:00", 12.0)
        r = ChanAnalysisResult(symbol="X", bars_count=100, signals=[sig], latest_signal=sig)
        r.recommendation = Recommendation(
            action="buy", action_label="", bias="bullish", score=2.0,
        )
        raw = build_raw_signal("X", "x", r)
        assert raw is not None
        assert raw.date == "2026-09-19"


class TestAggregateDays:
    def test_buckets_by_date_desc(self):
        raw = [
            _raw("A", "2026-09-17", "buy", 0.5),
            _raw("B", "2026-09-19", "sell", 0.9),
            _raw("C", "2026-09-18", "buy", 0.7),
        ]
        days = aggregate_days(raw, days=8, top_n=10)
        assert [d.date for d in days] == ["2026-09-19", "2026-09-18", "2026-09-17"]

    def test_top_n_limits_and_sorts_by_strength_desc(self):
        raw = [_raw(f"S{i}", "2026-09-19", "buy", i / 20) for i in range(15)]
        days = aggregate_days(raw, days=8, top_n=10)
        assert len(days) == 1
        signals = days[0].signals
        assert len(signals) == 10
        strengths = [s.strength for s in signals]
        assert strengths == sorted(strengths, reverse=True)
        # 只保留最强的 10 个（强度 >= 5/20）
        assert min(strengths) >= 5 / 20

    def test_counts_buy_and_sell(self):
        raw = [
            _raw("A", "2026-09-19", "buy", 0.9),
            _raw("B", "2026-09-19", "buy", 0.8),
            _raw("C", "2026-09-19", "sell", 0.7),
        ]
        days = aggregate_days(raw, days=8, top_n=10)
        assert days[0].buy_count == 2
        assert days[0].sell_count == 1

    def test_days_limit(self):
        raw = [_raw(f"S{i}", f"2026-09-{10 + i:02d}", "buy", 0.5) for i in range(8)]
        days = aggregate_days(raw, days=3, top_n=10)
        assert len(days) == 3
        # 最新三天
        assert [d.date for d in days] == ["2026-09-17", "2026-09-16", "2026-09-15"]

    def test_empty(self):
        assert aggregate_days([], days=8, top_n=10) == []
