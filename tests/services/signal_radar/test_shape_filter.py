"""雷达形态有效性筛选，不改变详情信号或新增行情扫描。"""
from copy import deepcopy
from datetime import date

import pytest

from app.services.chan.analyzer import ChanAnalyzer
from app.services.chan.shape_filters import ShapeState
from app.services.signal_radar import service as svc
from tests.services.chan.test_signals import _decaying_downtrend_bars
from tests.services.signal_radar.test_service import _FakeRedis, _raw, _sig


@pytest.mark.parametrize(("side", "extreme", "close"), [("buy", 99, 102), ("sell", 101, 98)])
def test_wick_break_invalidates_even_when_close_recovers(side: str, extreme: float, close: float) -> None:
    key = "low" if side == "buy" else "high"
    bars = [
        {"time": "2026-09-22", key: extreme, "close": close},
        {"time": "2026-09-21", key: extreme, "close": close},
        {"time": "2026-09-20", key: extreme, "close": close},
    ]
    assert svc._invalidated_on(side == "buy", 100, "2026-09-20", bars) == "2026-09-21"


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_touching_shape_level_does_not_invalidate(side: str) -> None:
    bars = [{"time": "2026-09-21", "low": 100, "high": 100, "close": 100}]
    assert svc._invalidated_on(side == "buy", 100, "2026-09-20", bars) is None


def test_historical_day_cannot_use_later_confirmation() -> None:
    signal = _raw("X", "2026-09-20", "buy", 0.8)
    signal.confirmed_on = "2026-09-22"
    days = svc.build_days([[signal]], ["2026-09-23", "2026-09-22", "2026-09-21"], top_n=10)
    assert [day.buy_count for day in days] == [1, 1, 0]


@pytest.mark.parametrize("unconfirmed", [True, False])
def test_rejected_latest_signal_does_not_revive_older_one(unconfirmed: bool) -> None:
    older = _raw("X", "2026-09-20", "buy", 0.8)
    latest = _raw("X", "2026-09-21", "sell", 0.8)
    latest.confirmed = not unconfirmed
    latest.invalidated_on = None if unconfirmed else "2026-09-22"
    assert svc.build_days([[older, latest]], ["2026-09-22"], top_n=10)[0].signals == []


def test_real_analysis_supplies_confirmation_times_without_mutating_details() -> None:
    result = ChanAnalyzer().analyze("X", _decaying_downtrend_bars(), mode="loose")
    assert result.stroke_done_at
    assert any(not signal.confirmed for signal in result.signals)
    original = deepcopy(result.signals)
    history = svc.build_signal_history("X", "测试", result)
    for raw, signal in zip(history, sorted(original, key=lambda s: s.detected_time or s.time), strict=True):
        if raw.confirmed:
            assert raw.confirmed_on is not None
            assert raw.confirmed_on >= signal.time[:10]
    assert result.signals == original


async def test_scan_does_not_fill_empty_slots_with_unconfirmed_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    day = date.today().isoformat()
    result = svc.ChanAnalysisResult(symbol="X", bars_count=100)
    candidate = _sig("buy3", day, 10)
    candidate.confirmed = False
    result.candidate_signals = [candidate]

    async def fake_scan(*args, **kwargs):
        return [], None, result, [day]

    async def fake_kline(**kwargs):
        return []

    async def fake_attach(pool, **kwargs):
        assert pool.signals == []

    monkeypatch.setattr(svc, "_scan_symbol", fake_scan)
    monkeypatch.setattr(svc, "fetch_kline", fake_kline)
    monkeypatch.setattr(svc, "attach_sub_levels", fake_attach)
    response = await svc.compute_market("us", redis=_FakeRedis(), user_id=7, watchlist=[("X", "测试")])
    assert response.days
    assert all(not day.signals and not day.candidates for day in response.days)
    assert result.candidate_signals == [candidate]


def test_shape_filter_invalidates_all_radar_cache_types() -> None:
    assert all(":shape2:" in key for key in [
        svc._cache_key("us", "nasdaq100"),
        svc.watchlist_cache_key("us", 7, [("X", "测试")]),
        svc._demo_cache_key("us", "nasdaq100", "2026-09-01"),
    ])


# ---- czsc 形态过滤：shape_rejected 出生即剔除、不回退旧信号 ----
def test_shape_rejected_latest_signal_excluded_without_fallback() -> None:
    """最新信号被形态过滤剔除后，该 symbol 当日无信号，旧信号不得回锅上榜。"""
    older = _raw("X", "2026-09-20", "buy", 0.8)
    latest = _raw("X", "2026-09-21", "buy", 0.9)
    latest.shape_rejected = "窄幅震荡"
    days = svc.build_days([[older, latest]], ["2026-09-22"], top_n=10)
    assert days[0].signals == []
    # 对照：未被剔除的旧信号单独存在时正常上榜
    days = svc.build_days([[older]], ["2026-09-22"], top_n=10)
    assert [s.symbol for s in days[0].signals] == ["X"]


def test_build_signal_history_marks_shape_rejected_by_signal_day() -> None:
    """按信号所属笔终点日（sig.time 的日期部分）查形态状态表，命中即标记过滤器名。"""
    rejected = _sig("buy1", "2026-09-10", 10.0)
    kept = _sig("sell1", "2026-09-15", 12.0)
    missing = _sig("buy2", "2026-09-18", 11.0)  # 查不到形态状态：不剔
    result = svc.ChanAnalysisResult(
        symbol="X", bars_count=100, signals=[rejected, kept, missing],
        shape_states={
            "2026-09-10": ShapeState(narrow_range=True, close_pos="高位"),
            "2026-09-15": ShapeState(close_pos="低位", volatility="中波动"),
        },
    )
    history = svc.build_signal_history("X", "测试", result)
    by_type = {r.signal_type: r.shape_rejected for r in history}
    assert by_type == {"buy1": "窄幅震荡", "sell1": None, "buy2": None}


def test_build_signal_history_logs_rejection_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    """剔除分布按过滤器名计数记 debug 日志（可观测）；无剔除时不记。"""
    events: list[tuple[str, dict]] = []

    class _Spy:
        def debug(self, event: str, **kw: object) -> None:
            events.append((event, kw))

        def __getattr__(self, name: str):
            return lambda *a, **k: None

    monkeypatch.setattr(svc, "logger", _Spy())
    sig = _sig("buy1", "2026-09-10", 10.0)
    result = svc.ChanAnalysisResult(
        symbol="X", bars_count=100, signals=[sig],
        shape_states={"2026-09-10": ShapeState(fake_break="看空", close_pos="高位")},
    )
    svc.build_signal_history("X", "测试", result)
    logged = [kw for e, kw in events if e == "signal_radar_shape_rejected"]
    assert logged == [{"symbol": "X", "counts": {"假突破": 1}}]

    events.clear()
    clean = svc.ChanAnalysisResult(symbol="X", bars_count=100, signals=[sig])
    svc.build_signal_history("X", "测试", clean)
    assert not [e for e, _ in events if e == "signal_radar_shape_rejected"]


def test_real_analysis_shape_marks_are_valid_filter_names() -> None:
    """真实分析链路：开 shape_filters 后标记值只可能是 None 或五个过滤器名，且不改信号条数。"""
    result = ChanAnalyzer().analyze("X", _decaying_downtrend_bars(), mode="loose",
                                    shape_filters=True)
    history = svc.build_signal_history("X", "测试", result)
    valid = {None, "假突破", "窄幅震荡", "收盘位置", "低波动", "区间震荡"}
    assert {r.shape_rejected for r in history} <= valid
    assert len(history) == len(result.signals)
    # 开关真实生效：有逐日形态状态，且这份数据稳定剔除至少一条（空表时上面的集合断言也会过）
    assert result.shape_states
    assert any(r.shape_rejected for r in history)


async def test_scan_symbol_enables_shape_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    """雷达扫描路径的 analyze 必须开 shape_filters（形态状态进入历史标记链路）。"""
    seen: dict[str, object] = {}

    class _SpyAnalyzer:
        def analyze(self, symbol: str, bars: list[dict], **kwargs: object) -> svc.ChanAnalysisResult:
            seen["shape_filters"] = kwargs.get("shape_filters")
            return svc.ChanAnalysisResult(symbol=symbol, bars_count=len(bars))

    async def fake_fetch(**kwargs: object) -> list[dict]:
        return [{"time": "2026-09-20", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100}]

    monkeypatch.setattr(svc, "_analyzer", _SpyAnalyzer())
    monkeypatch.setattr(svc, "fetch_kline", fake_fetch)
    await svc._scan_symbol("X", "测试", user_id=None, start_date="2026-08-01",
                           end_date="2026-09-20", redis=_FakeRedis())
    assert seen["shape_filters"] is True
