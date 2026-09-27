"""雷达 MA20 展示过滤：不改变缠论原始买卖点。"""
from datetime import date, timedelta

import pytest

from app.services.chan.analyzer import ChanAnalysisResult
from app.services.chan.signals import Signal
from app.services.signal_radar import service as svc


def _bars(last: float = 12.0) -> list[dict]:
    return [
        {"time": (date(2026, 9, 1) + timedelta(days=i)).isoformat(),
         "close": 10.0 if i < 19 else last}
        for i in range(20)
    ]


def _result(side: str = "buy") -> ChanAnalysisResult:
    signal = Signal(
        type=f"{side}2", time="2026-09-20", price=5 if side == "buy" else 15,
        strength="strong", divergence=None, description="", confirmed=True, lang="zh",
    )
    return ChanAnalysisResult(symbol="X", bars_count=20, signals=[signal], candidate_signals=[signal])


@pytest.mark.parametrize(("close", "side"), [(12, "buy"), (8, "sell"), (10, None)])
def test_ma20_direction_and_warmup(close: float, side: str | None) -> None:
    positions = svc.moving_average_sides(list(reversed(_bars(close))))
    assert positions.get("2026-09-20") == side
    assert "2026-09-19" not in positions


@pytest.mark.parametrize("close", [None, float("nan"), float("inf"), 0, -1])
def test_invalid_close_does_not_pass(close: float | None) -> None:
    bars = _bars()
    bars[10]["close"] = close
    assert svc.moving_average_sides(bars) == {}


def test_filter_changes_with_display_day_without_future_prices() -> None:
    bars = _bars() + [{"time": "2026-09-21", "close": 8.0}]
    result = _result()
    history = svc.build_signal_history("X", "测试", result, bars)
    days = svc.build_days(
        [history], ["2026-09-21", "2026-09-20"], top_n=10,
        today=date(2026, 9, 21),
    )
    assert days[0].signals == []
    assert len(days[1].signals) == 1
    assert days[1].buy_count == 1
    assert result.signals == [_result().signals[0]]
    assert svc.moving_average_sides(bars)["2026-09-20"] == svc.moving_average_sides(_bars())["2026-09-20"]


def test_filtered_latest_signal_does_not_revive_older_signal() -> None:
    bars = _bars()
    result = _result("sell")
    older = _result("buy").signals[0]
    older.time = "2026-09-19"
    result.signals.insert(0, older)
    history = svc.build_signal_history("X", "测试", result, bars)
    assert svc.build_days([history], ["2026-09-20"], top_n=10)[0].signals == []


def test_filter_runs_before_top_n_and_also_filters_candidates() -> None:
    bars = _bars()
    buy = svc.build_signal_history("BUY", "买点", _result(), bars)
    sell = svc.build_signal_history("SELL", "卖点", _result("sell"), bars)
    sell[0].strength = 1.0
    day = svc.build_days([sell, buy], ["2026-09-20"], top_n=1)[0]
    assert [s.symbol for s in day.signals] == ["BUY"]
    assert (day.buy_count, day.sell_count) == (1, 0)
    candidates = svc.build_candidates("SELL", "卖点", _result("sell"), bars)
    assert svc.pick_candidates(candidates, day.date, [day.date], taken=set(), slots=10) == []
    candidates = svc.build_candidates("BUY", "买点", _result(), bars)
    assert len(svc.pick_candidates(candidates, day.date, [day.date], taken=set(), slots=10)) == 1


def test_missing_day_or_insufficient_history_does_not_pass() -> None:
    for bars in ([], _bars()[:19]):
        history = svc.build_signal_history("X", "测试", _result(), bars)
        assert svc.build_days([history], ["2026-09-20"], top_n=10)[0].signals == []
    history = svc.build_signal_history("X", "测试", _result(), _bars())
    assert svc.build_days([history], ["2026-09-21"], top_n=10)[0].signals == []


def test_all_radar_cache_types_include_filter_version() -> None:
    keys = [
        svc._cache_key("us", "nasdaq100"),
        svc.watchlist_cache_key("us", 1, [("X", "测试")]),
        svc._demo_cache_key("us", "nasdaq100", "2026-09-01"),
    ]
    assert all(":ma20v1:" in key for key in keys)


async def test_scan_supplies_ma_data_to_signals_and_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch(**kwargs: object) -> list[dict]:
        return _bars()

    monkeypatch.setattr(svc, "fetch_kline", fake_fetch)
    monkeypatch.setattr(svc._analyzer, "analyze", lambda *args, **kwargs: _result())
    history, failure, candidates, _ = await svc._scan_symbol(
        "X", "测试", user_id=None, start_date="2026-09-01", end_date="2026-09-20",
        redis=None,  # type: ignore[arg-type]
    )
    assert failure is None
    assert history[0].ma_sides == candidates[0].ma_sides == {"2026-09-20": "buy"}
