"""评级准入、历史时点和雷达完整候选池回归。"""

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


def test_threshold_is_grade_not_raw_score_and_serializes():
    signals = [signal(s) for s in ("A", "B", "C", "D", "E")]
    day = RadarDayOut(date=str(DAY), buy_count=5, sell_count=0, signals=signals, candidates=signals)
    history = {"A": [grade()], "B": [grade("B+", 90)], "C": [grade("C+", 99)],
               "D": [grade(None)], "E": [grade("A+", 88)]}
    out = qf.apply_filter(day, history, list(history))
    assert [s.symbol for s in out.signals] == ["A", "E"]
    assert [s.symbol for s in out.candidates] == ["A", "E"]
    restored = RadarDayOut.model_validate_json(out.model_dump_json())
    assert restored.signals[0].quant_score == 65
    assert restored.quant_filter.eligible == 2
    assert restored.quant_filter.below_threshold == 2
    assert restored.quant_filter.missing == 1
    assert restored.buy_count == 2


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
    out = qf.apply_filter(day, {"B": [grade("F")]}, ["A", "B", "C"], preserve_sells=True)
    assert [s.symbol for s in out.signals] == ["B", "C"]
    assert out.sell_count == 2 and out.buy_count == 0
    assert out.quant_filter.preserve_sells


def test_row_available_date_and_invalid_scores():
    row = QuantResult(market="us", symbol="A", as_of=DAY, sector_key="tech",
                      created_at=datetime(2026, 9, 30), updated_at=datetime(2026, 10, 1),
                      payload_zh={"overall": {"grade": "A", "score": float("nan")}})
    entry = qf.grade_from_row(row)
    assert entry.available_on == date(2026, 10, 1) and entry.score is None
    row.payload_zh["as_of"] = {"filing_date": "2026-10-02"}
    assert qf.grade_from_row(row).available_on == date(2026, 10, 2)


def test_quant_only_breaks_technical_ties():
    a = signal("A").model_copy(update={"quant_status": "eligible", "quant_score": 60})
    b = signal("B").model_copy(update={"quant_status": "eligible", "quant_score": 80})
    c = signal("C", strength=0.9).model_copy(update={"quant_status": "eligible", "quant_score": 50})
    out = svc.rerank_with_resonance(RadarDayOut(date=str(DAY), buy_count=3, sell_count=0, signals=[a,b,c]), 3)
    assert [s.symbol for s in out.signals] == ["C", "B", "A"]


@pytest.mark.parametrize("market", ["us", "hk", "cn"])
async def test_full_pool_filtered_before_top_n_and_candidates(monkeypatch, market):
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
    if market == "us":
        assert seen == ["S23"]
        assert [s.symbol for s in day.signals] == ["S23"]
        assert [s.symbol for s in day.candidates] == ["S24"]
        assert day.quant_filter.eligible == 2
        state.demo_nominal = str(DAY)
        demo = await svc._assemble_demo(state)
        assert [s.symbol for s in demo.days[0].signals] == ["S23"]
        assert demo.days[0].quant_filter.eligible == 2
        class NoWriteRedis:
            async def set(self, *args, **kwargs):
                raise AssertionError("查询故障不能写缓存")
        day.quant_filter.status = "unavailable"
        assert await svc._publish(state, response, redis=NoWriteRedis()) is response
        demo.days[0].quant_filter.status = "unavailable"
        await svc._publish_demo(state, demo, redis=NoWriteRedis())
    else:
        assert len(day.signals) == 3 and day.quant_filter is None


async def test_query_failure_is_distinct_from_no_data(monkeypatch):
    async def fail(*args):
        raise RuntimeError("测试数据库故障")
    monkeypatch.setattr(qf.repository, "get_quant_grade_history", fail)
    assert await qf.load_grades("us", ["A"], [str(DAY)]) is None
    day = RadarDayOut(date=str(DAY), buy_count=1, sell_count=0, signals=[signal("A")])
    assert qf.apply_filter(day, None, ["A"]).quant_filter.status == "unavailable"
    assert qf.apply_filter(day, {}, ["A"]).quant_filter.status == "ready"


@pytest.mark.parametrize("failed", [False, True])
async def test_index_prefilter_precedes_stock_calculation(monkeypatch, failed):
    """未达标、缺失与过期股票不调用个股扫描；合格股票算完才取前十。"""
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
        assert events[0] == "grades"
        events.append(symbol)
        raw = svc.RawSignal(symbol=symbol, name=symbol, side="buy", label="二买", signal_type="buy2",
                            date=str(today), price=1, strength=0.8, bias="bullish",
                            signal_strength="strong", confirmed=True, pivot_stage_depth=0.5)
        return [raw], None, None, [str(today)]
    async def attach(*args, **kwargs):
        pass
    async def publish(state, response, **kwargs):
        assert state.scan_count == (0 if failed else 12)
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
    assert len(response.days[0].signals) == (0 if failed else 10)
    assert set(events[1:]) == (set() if failed else set(eligible))
    assert events.count("grades") == 1


async def test_prefilter_keeps_historical_eligible_union_and_skips_watchlist(monkeypatch):
    async def bars(**kwargs):
        return [{"time": "2026-09-29"}, {"time": "2026-09-30"}]
    async def load(*args):
        return {"PAST": [grade("B+"), grade(day=date(2026, 9, 29), available=date(2026, 9, 29))],
                "NOW": [grade()], "LOW": [grade("B+")]}
    monkeypatch.setattr(svc, "fetch_kline", bars)
    monkeypatch.setattr(qf, "load_grades", load)
    state = svc._ScanState(market="us", universe=get_universe("us"), is_watchlist=False,
                           constituents=[(s,s) for s in ["PAST", "NOW", "LOW"]], user_id=None,
                           mode="loose", days=2, top_n=10, max_age_days=25, start_date="2026-01-01",
                           end_date=str(DAY), cutoff="2026-09-01")
    assert [s for s, _ in await svc._prefilter_constituents(state, redis=None)] == ["PAST", "NOW"]
    assert qf.grade_on(state.quant_grades, "PAST", DAY)[1] == "below_threshold"
    state.is_watchlist = True
    assert await svc._prefilter_constituents(state, redis=None) == state.constituents

    state.is_watchlist = False
    state.scan_count = 0
    state.quant_grades = {}
    state.demo_nominal = str(DAY)
    class RecordingRedis:
        written = False
        async def set(self, *args, **kwargs):
            self.written = True
    redis = RecordingRedis()
    empty = await svc._assemble_demo(state)
    await svc._publish_demo(state, empty, redis=redis)
    assert redis.written and empty.days[0].signals == []
