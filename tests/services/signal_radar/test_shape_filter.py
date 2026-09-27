"""雷达 czsc 形态过滤（当前暂停应用，代码保留）与雷达筛选缓存版本。"""
import pytest

from app.services.chan.analyzer import ChanAnalyzer
from app.services.chan.shape_filters import ShapeState
from app.services.signal_radar import service as svc
from tests.services.chan.test_signals import _decaying_downtrend_bars
from tests.services.signal_radar.test_service import _FakeRedis, _raw, _sig


def test_radar_filter_version_isolates_all_cache_types() -> None:
    assert all(":shape5:" in key for key in [
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


def test_build_signal_history_marks_shape_rejected_by_detected_day() -> None:
    """按信号成立日（detected_time，雷达展示的日期）查形态状态表，不看笔终点日。

    笔终点是分型极值那根K线，其形态天然偏向信号反面，用它判定会系统性误剔。
    """
    # 笔终点日窄幅震荡、成立日干净：保留
    kept = _sig("buy1", "2026-09-10", 10.0)
    kept.detected_time = "2026-09-14"
    # 笔终点日干净、成立日低波动：剔除
    rejected = _sig("sell1", "2026-09-15", 12.0)
    rejected.detected_time = "2026-09-17"
    # 没有成立日：回退笔终点日（窄幅震荡）
    fallback = _sig("buy2", "2026-09-18", 11.0)
    # 查不到形态状态：不剔
    missing = _sig("buy3", "2026-09-21", 11.0)
    result = svc.ChanAnalysisResult(
        symbol="X", bars_count=100, signals=[kept, rejected, fallback, missing],
        shape_states={
            "2026-09-10": ShapeState(narrow_range=True),
            "2026-09-14": ShapeState(volatility="中波动"),
            "2026-09-15": ShapeState(volatility="中波动"),
            "2026-09-17": ShapeState(volatility="低波动"),
            "2026-09-18": ShapeState(narrow_range=True),
        },
    )
    history = svc.build_signal_history("X", "测试", result)
    by_type = {r.signal_type: r.shape_rejected for r in history}
    assert by_type == {"buy1": None, "sell1": "低波动", "buy2": "窄幅震荡", "buy3": None}


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
        shape_states={"2026-09-10": ShapeState(fake_break="看空")},
    )
    svc.build_signal_history("X", "测试", result)
    logged = [kw for e, kw in events if e == "signal_radar_shape_rejected"]
    assert logged == [{"symbol": "X", "counts": {"假突破": 1}}]

    events.clear()
    clean = svc.ChanAnalysisResult(symbol="X", bars_count=100, signals=[sig])
    svc.build_signal_history("X", "测试", clean)
    assert not [e for e, _ in events if e == "signal_radar_shape_rejected"]


def test_real_analysis_shape_marks_are_valid_filter_names() -> None:
    """真实分析链路：开 shape_filters 后标记值只可能是 None 或三个过滤器名，且不改信号条数。"""
    result = ChanAnalyzer().analyze("X", _decaying_downtrend_bars(), mode="loose",
                                    shape_filters=True)
    history = svc.build_signal_history("X", "测试", result)
    valid = {None, "假突破", "窄幅震荡", "低波动"}
    assert {r.shape_rejected for r in history} <= valid
    assert len(history) == len(result.signals)
    # 开关真实生效，且每条信号的成立日都能在形态状态表里查到：查不到时 reject_reason(None)
    # 静默不剔，规则形同虚设（日期格式或预热段错位都会造成这种情况）
    assert result.shape_states
    assert result.signals
    for sig in result.signals:
        assert (sig.detected_time or sig.time)[:10] in result.shape_states, sig


@pytest.mark.parametrize("enabled", [False, True])
async def test_scan_symbol_shape_filters_follow_switch(
    monkeypatch: pytest.MonkeyPatch, enabled: bool,
) -> None:
    """雷达扫描是否开形态过滤只由 _SHAPE_FILTERS_ENABLED 决定（当前默认关闭，代码保留）。"""
    seen: dict[str, object] = {}

    class _SpyAnalyzer:
        def analyze(self, symbol: str, bars: list[dict], **kwargs: object) -> svc.ChanAnalysisResult:
            seen["shape_filters"] = kwargs.get("shape_filters")
            return svc.ChanAnalysisResult(symbol=symbol, bars_count=len(bars))

    async def fake_fetch(**kwargs: object) -> list[dict]:
        return [{"time": "2026-09-20", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100}]

    monkeypatch.setattr(svc, "_analyzer", _SpyAnalyzer())
    monkeypatch.setattr(svc, "fetch_kline", fake_fetch)
    monkeypatch.setattr(svc, "_SHAPE_FILTERS_ENABLED", enabled)
    await svc._scan_symbol("X", "测试", user_id=None, start_date="2026-08-01",
                           end_date="2026-09-20", redis=_FakeRedis())
    assert seen["shape_filters"] is enabled


def test_shape_filters_disabled_by_default() -> None:
    assert svc._SHAPE_FILTERS_ENABLED is False
