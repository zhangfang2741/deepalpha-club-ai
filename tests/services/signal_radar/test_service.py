"""信号雷达纯聚合逻辑单测（无 IO）。"""
from __future__ import annotations

from app.services.chan.analyzer import ChanAnalysisResult
from app.services.chan.signals import Signal
from app.services.signal_radar.service import (
    RawSignal,
    build_days,
    build_signal_history,
    display_rank,
    signal_strength,
)


def _sig(sig_type: str, time: str, price: float, strength: str = "medium") -> Signal:
    return Signal(
        type=sig_type, time=time, price=price, strength=strength,
        divergence=None, description="", confirmed=True, lang="zh",
    )


def _raw(symbol: str, day: str, side: str, strength: float, level: int = 1) -> RawSignal:
    return RawSignal(
        symbol=symbol, name=symbol, side=side, label="一买" if side == "buy" else "一卖",
        signal_type=f"{side}{level}", date=day, price=10.0,
        strength=strength, bias="bullish" if side == "buy" else "bearish",
        signal_strength="medium", confirmed=True,
    )


class TestSignalStrength:
    def test_known_labels(self):
        assert signal_strength("strong") == 0.8
        assert signal_strength("medium") == 0.55
        assert signal_strength("weak") == 0.35

    def test_unknown_label_defaults_to_mid(self):
        assert signal_strength("???") == 0.5


class TestBuildSignalHistory:
    def test_empty_when_no_signals(self):
        r = ChanAnalysisResult(symbol="X", bars_count=100)
        assert build_signal_history("X", "测试", r) == []

    def test_returns_all_signals_sorted_by_date(self):
        s1 = _sig("buy1", "2026-09-01", 10.0)
        s2 = _sig("sell1", "2026-09-10", 12.0)
        r = ChanAnalysisResult(symbol="X", bars_count=100, signals=[s2, s1])
        history = build_signal_history("NVDA", "英伟达", r)
        assert [h.date for h in history] == ["2026-09-01", "2026-09-10"]
        assert history[0].side == "buy"
        assert history[1].side == "sell"
        assert all(h.name == "英伟达" for h in history)

    def test_date_is_truncated_to_day(self):
        sig = _sig("buy1", "2026-09-19T00:00:00", 12.0)
        r = ChanAnalysisResult(symbol="X", bars_count=100, signals=[sig])
        history = build_signal_history("X", "x", r)
        assert history[0].date == "2026-09-19"

    def test_strength_from_signal_label_not_score(self):
        sig = _sig("sell1", "2026-09-18", 50.0, strength="strong")
        r = ChanAnalysisResult(symbol="X", bars_count=100, signals=[sig])
        history = build_signal_history("AAPL", "苹果", r)
        assert history[0].strength == signal_strength("strong")
        assert history[0].bias == "bearish"


class TestBuildDays:
    def test_signal_stays_active_until_superseded(self):
        """一只股票 09-01 出现买点、09-10 前无新信号——09-01~09-09 每天都在场，09-10 起换新信号。"""
        history = [_raw("A", "2026-09-01", "buy", 0.5), _raw("A", "2026-09-10", "sell", 0.9)]
        days = build_days([history], ["2026-09-05", "2026-09-01"], top_n=10)
        assert [s.date for s in days[0].signals] == ["2026-09-01"]
        assert days[0].signals[0].side == "buy"
        assert [s.date for s in days[1].signals] == ["2026-09-01"]

    def test_symbol_absent_before_its_first_signal(self):
        history = [_raw("A", "2026-09-10", "buy", 0.5)]
        days = build_days([history], ["2026-09-05"], top_n=10)
        assert days[0].signals == []
        assert days[0].buy_count == 0

    def test_top_n_limits_and_sorts_by_strength_when_same_level(self):
        """同为一类时，重要度随强弱单调——前 top_n 仍按 strength 从高到低。"""
        histories = [[_raw(f"S{i}", "2026-09-19", "buy", i / 20)] for i in range(15)]
        days = build_days(histories, ["2026-09-19"], top_n=10)
        assert len(days) == 1
        signals = days[0].signals
        assert len(signals) == 10
        strengths = [s.strength for s in signals]
        assert strengths == sorted(strengths, reverse=True)
        assert min(strengths) >= 5 / 20

    def test_big_pale_signal_outranks_small_dark_in_cull(self):
        """淘汰按'潜在空间+强弱'综合：一类弱背驰(大而淡)排在三类强背驰(小而深)之前。"""
        histories = [
            [_raw("BIG", "2026-09-19", "buy", 0.35, level=1)],   # 大而淡
            [_raw("SMALL", "2026-09-19", "buy", 0.8, level=3)],  # 小而深
        ]
        days = build_days(histories, ["2026-09-19"], top_n=1)
        assert [s.symbol for s in days[0].signals] == ["BIG"]

    def test_small_pale_signal_culled_first(self):
        """看板满员时最先淘汰'小而淡'(三类弱)，大或深的留下。"""
        histories = [
            [_raw("A", "2026-09-19", "buy", 0.8, level=1)],   # 大而深
            [_raw("B", "2026-09-19", "buy", 0.35, level=1)],  # 大而淡
            [_raw("C", "2026-09-19", "buy", 0.8, level=3)],   # 小而深
            [_raw("D", "2026-09-19", "buy", 0.35, level=3)],  # 小而淡 → 被淘汰
        ]
        days = build_days(histories, ["2026-09-19"], top_n=3)
        kept = {s.symbol for s in days[0].signals}
        assert kept == {"A", "B", "C"}
        assert "D" not in kept


class TestDisplayRank:
    def test_level_read_from_signal_type_suffix(self):
        assert display_rank(_raw("X", "2026-09-19", "buy", 0.5, level=1)) > display_rank(
            _raw("X", "2026-09-19", "buy", 0.5, level=2)
        )
        assert display_rank(_raw("X", "2026-09-19", "buy", 0.5, level=2)) > display_rank(
            _raw("X", "2026-09-19", "buy", 0.5, level=3)
        )

    def test_potential_space_can_outweigh_strength(self):
        """0.6/0.4 权重下，一类弱(大而淡)重要度高于三类强(小而深)。"""
        big_pale = _raw("BIG", "2026-09-19", "buy", 0.35, level=1)
        small_dark = _raw("SMALL", "2026-09-19", "buy", 0.8, level=3)
        assert display_rank(big_pale) > display_rank(small_dark)

    def test_counts_buy_and_sell(self):
        histories = [
            [_raw("A", "2026-09-19", "buy", 0.9)],
            [_raw("B", "2026-09-19", "buy", 0.8)],
            [_raw("C", "2026-09-19", "sell", 0.7)],
        ]
        days = build_days(histories, ["2026-09-19"], top_n=10)
        assert days[0].buy_count == 2
        assert days[0].sell_count == 1

    def test_returns_one_entry_per_requested_day_in_order(self):
        histories = [[_raw("A", "2026-09-10", "buy", 0.5)]]
        requested = ["2026-09-17", "2026-09-16", "2026-09-15"]
        days = build_days(histories, requested, top_n=10)
        assert [d.date for d in days] == requested

    def test_no_histories_still_returns_a_day_with_zero_counts(self):
        """trading_days 独立传入（来自 ETF 日历）：无任何股票有信号时，那天仍要出现（空桶），不能连日期都消失。"""
        days = build_days([], ["2026-09-19"], top_n=10)
        assert len(days) == 1
        assert days[0].date == "2026-09-19"
        assert days[0].signals == []

    def test_no_requested_days_returns_empty(self):
        history = [_raw("A", "2026-09-19", "buy", 0.5)]
        assert build_days([history], [], top_n=10) == []

    def test_signal_expires_after_max_age(self):
        """在场信号诞生超过 max_age_days 天后不再展示（09-01 买点在 34 天后的 10-05 已过期）。"""
        history = [_raw("A", "2026-09-01", "buy", 0.5)]
        days = build_days([history], ["2026-10-05"], top_n=10, max_age_days=30)
        assert days[0].signals == []
        assert days[0].buy_count == 0

    def test_signal_visible_at_exactly_max_age(self):
        """恰好等于 max_age_days 天仍在场（09-01 买点在 30 天后的 10-01 边界含、应显示）。"""
        history = [_raw("A", "2026-09-01", "buy", 0.5)]
        days = build_days([history], ["2026-10-01"], top_n=10, max_age_days=30)
        assert [s.date for s in days[0].signals] == ["2026-09-01"]

    def test_expiry_is_relative_to_each_viewed_day(self):
        """过期相对每个展示日各自判断：同条 09-01 信号翻看 09-15 在场、10-05 已过期。"""
        history = [_raw("A", "2026-09-01", "buy", 0.5)]
        days = build_days([history], ["2026-10-05", "2026-09-15"], top_n=10, max_age_days=30)
        assert days[0].signals == []  # 10-05：过期
        assert [s.date for s in days[1].signals] == ["2026-09-01"]  # 09-15：在场
