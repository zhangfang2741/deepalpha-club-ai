"""评级展示（暂不参与排序）、历史时点和雷达完整候选池回归。"""

from datetime import date, datetime

import pytest

from app.models.quant_research import QuantResult
from app.schemas.signal_radar import RadarDayOut, RadarSignalOut
from app.services.signal_radar import quant_filter as qf
from app.services.signal_radar import service as svc
from app.services.signal_radar.universe import get_universe

DAY = date(2026, 9, 30)


def signal(symbol, side="buy", strength=0.5):
    return RadarSignalOut(symbol=symbol, name=symbol, side=side, label="买点", signal_type=side + "2",
                          date=DAY.isoformat(), price=10, strength=strength, bias="neutral",
                          signal_strength="medium", confirmed=True, pivot_stage_depth=0.5)


def grade(value="A-", score=65, day=DAY, available=DAY):
    return qf.QuantGrade(value, score, day, available)


def test_all_grades_and_missing_data_retained_and_serialize():
    signals = [signal(s) for s in ("A", "B", "C", "D", "E")]
    day = RadarDayOut(date=str(DAY), buy_count=5, sell_count=0, signals=signals, candidates=signals)
    history = {"A": [grade()], "B": [grade("B+", 90)], "C": [grade("C+", 99)],
               "D": [grade(None)], "E": [grade("A+", 88)]}
    out = qf.attach_grades(day, history, list(history))
    assert [s.symbol for s in out.signals] == ["A", "B", "C", "D", "E"]
    assert [s.symbol for s in out.candidates] == ["A", "B", "C", "D", "E"]
    restored = RadarDayOut.model_validate_json(out.model_dump_json())
    assert restored.signals[0].quant_score == 65
    assert restored.quant_filter.eligible == 4
    assert restored.quant_filter.below_threshold == 0
    assert restored.quant_filter.missing == 1
    assert restored.buy_count == 5


def test_no_future_or_backfilled_grade_and_no_fallback_from_new_unrated():
    older = grade("A", day=date(2026, 9, 29), available=date(2026, 9, 29))
    future = grade("A+", day=date(2026, 10, 1), available=date(2026, 10, 1))
    backfill = grade("A+", available=date(2026, 10, 2))
    history = {"A": [future, backfill, older]}
    assert qf.grade_on(history, "A", DAY)[0] == older
    history["A"].append(grade(None))
    assert qf.grade_on(history, "A", DAY)[1] == "missing"


def test_stale_boundary_and_symbol_normalization():
    history = {"BRK-B": [grade(day=date(2026, 9, 23), available=date(2026, 9, 23))]}
    assert qf.grade_on(history, "BRK.B", DAY)[1] == "eligible"
    assert qf.grade_on(history, "BRK.B", date(2026, 10, 1))[1] == "stale"


def test_watchlist_sells_survive_missing_and_low_ratings():
    signals = [signal("A"), signal("B", "sell"), signal("C", "sell")]
    day = RadarDayOut(date=str(DAY), buy_count=1, sell_count=2, signals=signals)
    out = qf.attach_grades(day, {"B": [grade("F")]}, ["A", "B", "C"])
    assert [s.symbol for s in out.signals] == ["A", "B", "C"]
    assert out.sell_count == 2 and out.buy_count == 1
    assert out.quant_filter.mode == "marked"
    assert out.quant_filter.weight == 0.0


def test_row_available_date_and_invalid_scores():
    row = QuantResult(market="us", symbol="A", as_of=DAY, sector_key="tech",
                      created_at=datetime(2026, 9, 30), updated_at=datetime(2026, 10, 1),
                      payload_zh={"overall": {"grade": "A", "score": float("nan")}})
    entry = qf.grade_from_row(row)
    assert entry.available_on == date(2026, 10, 1) and entry.score is None
    row.payload_zh["as_of"] = {"filing_date": "2026-10-02"}
    assert qf.grade_from_row(row).available_on == date(2026, 10, 2)


def test_rating_marks_only_and_order_follows_technical_score():
    """评级只附加展示，排序回到纯技术分（2026-09-30 产品决定暂停权重）。"""
    a = signal("A", strength=0.5).model_copy(update={"quant_status": "eligible", "quant_grade": "F"})
    b = signal("B", strength=0.4).model_copy(update={"quant_status": "eligible", "quant_grade": "A+"})
    c = signal("C", strength=0.5).model_copy(update={"quant_status": "missing"})
    out = svc.rerank_with_resonance(RadarDayOut(date=str(DAY), buy_count=3, sell_count=0, signals=[a,b,c]), 3)
    assert [s.symbol for s in out.signals] == ["A", "C", "B"]
    assert qf.rating_factor(a) == 0 and qf.rating_factor(b) == 1 and qf.rating_factor(c) == 0.5
    assert qf.rating_factor(b.model_copy(update={"quant_status": "stale"})) == 0.5


def test_quant_rating_weight_disabled_for_now():
    """恢复权重时改回 0.5，并同步升雷达缓存键 _mode_ns 的版本。"""
    assert qf.QUANT_WEIGHT == 0.0


@pytest.mark.parametrize("market", ["us", "hk", "cn"])
async def test_all_markets_keep_technical_signals(monkeypatch, market):
    symbols = [f"S{i}" for i in range(25)]
    async def load(*args):
        assert market == "us"
        return {s: [grade("A-" if i >= 23 else "B+")] for i, s in enumerate(symbols)}
    async def bars(**kwargs):
        return [{"time": str(DAY)}]
    seen = []
    async def attach(day, **kwargs):
        seen.extend(s.symbol for s in day.signals)
    monkeypatch.setattr(qf, "load_grades", load)
    monkeypatch.setattr(svc, "fetch_kline", bars)
    monkeypatch.setattr(svc, "attach_sub_levels", attach)
    state = svc._ScanState(market=market, universe=get_universe(market), is_watchlist=False,
                           constituents=[(s,s) for s in symbols], user_id=None, mode="loose", days=1,
                           top_n=3, max_age_days=25, start_date="2026-01-01", end_date=str(DAY), cutoff=str(DAY))
    for i, symbol in enumerate(symbols):
        raw = svc.RawSignal(symbol=symbol, name=symbol, side="buy", label="买点", signal_type="buy2",
                            date=str(DAY), price=1, strength=1 - i / 100, bias="bullish",
                            signal_strength="medium", confirmed=True, pivot_stage_depth=0.5)
        state.results[symbol] = ([raw] if i < 24 else [], [raw] if i == 24 else [], [str(DAY)])
    response = await svc._assemble(state, redis=None)
    day = response.days[0]
    assert len(day.signals) == 3
    if market == "us":
        assert day.quant_filter.eligible == 25
        assert any(s.quant_grade == "B+" for s in day.signals)
        state.demo_nominal = str(DAY)
        demo = await svc._assemble_demo(state)
        assert len(demo.days[0].signals) == 10
    else:
        assert day.quant_filter is None


async def test_query_failure_is_distinct_from_no_data(monkeypatch):
    async def fail(*args):
        raise RuntimeError("测试数据库故障")
    monkeypatch.setattr(qf.repository, "get_quant_grade_history", fail)
    assert await qf.load_grades("us", ["A"], [str(DAY)]) is None
    day = RadarDayOut(date=str(DAY), buy_count=1, sell_count=0, signals=[signal("A")])
    assert qf.attach_grades(day, None, ["A"]).quant_filter.status == "unavailable"
    assert qf.attach_grades(day, {}, ["A"]).quant_filter.status == "ready"


@pytest.mark.parametrize("failed", [False, True])
async def test_full_index_scanned_even_when_ratings_fail(monkeypatch, failed):
    """全部股票都参与计算，评级缺失或查询失败仍产生前十。"""
    today = date.today()
    eligible = [f"PASS{i}" for i in range(12)]
    symbols = eligible + ["LOW", "MISSING", "STALE"]
    events = []
    async def resolve(*args, **kwargs):
        return [(s,s) for s in symbols]
    async def bars(**kwargs):
        return [{"time": str(today)}]
    async def load(market, requested, days):
        events.append("grades")
        if failed:
            return None
        return {**{s: [grade(day=today, available=today)] for s in eligible},
                "LOW": [grade("B+", day=today, available=today)],
                "STALE": [grade(day=date(2020, 1, 1), available=date(2020, 1, 1))]}
    async def scan(symbol, name, **kwargs):
        events.append(symbol)
        raw = svc.RawSignal(symbol=symbol, name=symbol, side="buy", label="二买", signal_type="buy2",
                            date=str(today), price=1, strength=0.8, bias="bullish",
                            signal_strength="strong", confirmed=True, pivot_stage_depth=0.5)
        return [raw], None, None, [str(today)]
    async def attach(*args, **kwargs):
        pass
    async def publish(state, response, **kwargs):
        return response
    monkeypatch.setattr(svc, "resolve_constituents", resolve)
    monkeypatch.setattr(svc, "fetch_kline", bars)
    monkeypatch.setattr(qf, "load_grades", load)
    monkeypatch.setattr(svc, "_scan_symbol", scan)
    monkeypatch.setattr(svc, "attach_sub_levels", attach)
    monkeypatch.setattr(svc, "_publish", publish)
    monkeypatch.setattr(svc, "_after_scan", attach)
    response = await svc.compute_market("us", redis=None, days=1)
    assert response.universe_size == 15
    assert len(response.days[0].signals) == 10
    assert set(events[:-1]) == set(symbols)
    assert events.count("grades") == 1


async def test_rating_outage_publishes_technical_snapshot(monkeypatch):
    signal_day = RadarDayOut(date=str(DAY), buy_count=1, sell_count=0, signals=[signal("A")])
    day = qf.attach_grades(signal_day, None, ["A"])
    assert len(day.signals) == 1
    response = svc.SignalRadarResponse(market="us", universe="nasdaq100", etf_name="纳指", universe_size=1,
                                        as_of=str(DAY), top_n=10, days=[day], status="ready")
    class Redis:
        stored = None
        ttl = None
        async def set(self, key, value, ex=None):
            self.stored = value
            self.ttl = ex
    redis = Redis()
    await svc._write_cache(redis, response)
    assert redis.ttl == 300
    restored = svc.SignalRadarResponse.model_validate_json(redis.stored)
    assert len(restored.days[0].signals) == 1
    assert restored.days[0].quant_filter.status == "unavailable"
