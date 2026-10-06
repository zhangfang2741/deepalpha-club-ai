"""「好股票」视图：只留当前综合等级达标的股票的买卖点。"""
from datetime import UTC, datetime

from app.schemas.signal_radar import RadarDayOut, RadarSignalOut, SignalRadarResponse
from app.services.signal_radar import quality_view as qv


def _sig(symbol, side="buy", sector="科技"):
    return RadarSignalOut(
        symbol=symbol, name=symbol, side=side, label="一买", signal_type=f"{side}1", date="2026-10-05", price=1.0,
        strength=0.5, bias="neutral", signal_strength="medium", confirmed=True, pivot_stage_depth=0.5,
        quant_grade="F", sector=sector)


GOOD = {"AAA": {"grade": "A+", "score": 80.0, "as_of": "2026-10-05"},
        "BBB": {"grade": "B+", "score": 60.0, "as_of": "2026-10-05"}}


def _pool(**counts):
    return [g for g, n in counts.items() for _ in range(n)]


def test_choose_cutoff_adapts_to_pool_and_respects_floor():
    # 沪深 300 类：285 只，目标 72，A+30 / A27 / A-21 累计 78 ≥ 72 → A-
    big = _pool(**{"A+": 30, "A": 27, "A-": 21, "B+": 16, "B": 6, "C": 185})
    assert qv.choose_cutoff(big) == "A-"
    # 恒生科技类：30 只，目标 max(8, 8)=8；A3 / A-3 / B2 累计 8 → B（整档纳入）
    small = _pool(**{"A": 3, "A-": 3, "B": 2, "B-": 1, "C+": 5, "F": 16})
    assert qv.choose_cutoff(small) == "B"
    # 池子整体偏弱：目标凑不够也不低于 B 的地板
    weak = _pool(**{"A": 1, "B-": 3, "C": 20})
    assert qv.choose_cutoff(weak) == "B"
    assert qv.choose_cutoff([]) == "B"


def test_choose_cutoff_never_cuts_inside_a_grade():
    # 目标 25% × 40 = 10：A+ 6 / A 6 累计 12 ≥ 10 → 整档纳入 A（共 12 只，不是 10 只）
    grades = _pool(**{"A+": 6, "A": 6, "B": 8, "D": 20})
    assert qv.choose_cutoff(grades) == "A"


def test_filter_day_keeps_good_overrides_grade_and_recounts():
    day = RadarDayOut(date="2026-10-05", buy_count=3, sell_count=1,
                      signals=[_sig("AAA"), _sig("ZZZ"), _sig("BBB", "sell", "能源"), _sig("YYY", "sell")],
                      candidates=[_sig("ZZZ"), _sig("AAA")])
    out = qv.filter_day(day, GOOD, {"AAA": (3, 1)})
    assert [s.symbol for s in out.signals] == ["AAA", "BBB"]
    a = out.signals[0]
    assert (a.quant_grade, a.quant_score, a.quant_status) == ("A+", 80.0, "eligible")   # 当前等级覆盖信号当天的
    assert (a.analyst_up, a.analyst_down) == (3, 1)
    assert out.signals[1].analyst_up is None
    assert (out.buy_count, out.sell_count) == (1, 1)
    assert out.sector_counts == {"科技": {"buy": 1, "sell": 0}, "能源": {"buy": 0, "sell": 1}}
    assert [s.symbol for s in out.candidates] == ["AAA"]


async def test_apply_quality_marks_response_and_survives_rating_failure(monkeypatch):
    resp = SignalRadarResponse(
        market="cn", universe="csi300", etf_name="沪深300", universe_size=300, as_of="2026-10-05", top_n=10,
        days=[RadarDayOut(date="2026-10-05", buy_count=2, sell_count=0, signals=[_sig("AAA"), _sig("ZZZ")])])
    now = datetime(2026, 10, 6, tzinfo=UTC)

    async def ok(market, universe, redis, now, mode="good"):
        return GOOD, 120, "B+"

    monkeypatch.setattr(qv, "good_stocks", ok)
    out = await qv.apply_quality(resp, None, now=now)    # type: ignore[arg-type]  # cn：不碰 analyst 缓存
    assert out.quality == "good" and out.quality_threshold == "B+"
    assert (out.quality_share, out.quality_min_count, out.quality_floor) == (0.25, 8, "B")  # 门槛选法随响应带给「怎么算的」说明
    assert (out.quality_good_count, out.quality_rated_count) == (2, 120)
    assert [s.symbol for s in out.days[0].signals] == ["AAA"]

    async def broken(market, universe, redis, now, mode="good"):
        return None

    monkeypatch.setattr(qv, "good_stocks", broken)
    same = await qv.apply_quality(resp, None, now=now)   # type: ignore[arg-type]
    assert same is resp                                   # 评级读取失败：原样返回，雷达不能因此变空


def _qg(grade, dims):
    from datetime import date

    from app.services.signal_radar.quant_filter import QuantGrade

    return QuantGrade(grade, 50.0, date(2026, 10, 5), date(2026, 10, 5), dim_scores=dims)


def test_ex_momentum_rescues_stock_vetoed_only_by_momentum():
    base = {"valuation": 80.0, "growth": 80.0, "profitability": 80.0, "revisions": 80.0}
    ranked = [
        ("GOOD", _qg("B", {**base, "momentum": 10.0})),   # 原口径被动量 F 一票否决封顶 C+
        ("MID", _qg("A", {k: 50.0 for k in (*base, "momentum")})),
        ("LOW", _qg("C", {k: 20.0 for k in (*base, "momentum")})),
    ]
    out = dict(qv.rerank_ex_momentum(ranked))
    assert out["GOOD"].score == 80.0 and out["GOOD"].grade == "A+"
    assert [s for s, _ in qv.rerank_ex_momentum(ranked)][0] == "GOOD"


def test_ex_momentum_keeps_veto_from_other_dimensions():
    ranked = [
        ("X", _qg("A", {"valuation": 95.0, "growth": 95.0, "profitability": 10.0, "momentum": 90.0})),
        ("Y", _qg("B", {"valuation": 40.0, "growth": 40.0, "profitability": 40.0, "momentum": 40.0})),
    ]
    out = dict(qv.rerank_ex_momentum(ranked))
    assert out["X"].grade in ("C+", "C", "C-", "D+", "D", "D-", "F")  # 封顶 C+


def test_ex_momentum_drops_stocks_without_dimension_detail():
    ranked = [("OLD", _qg("A", None)), ("ONLYM", _qg("A", {"momentum": 90.0}))]
    assert qv.rerank_ex_momentum(ranked) == []


async def test_good_stocks_ex_momentum_loads_dimension_scores(monkeypatch):
    """回归：评级历史查询不带维度明细，去动量口径必须单独补查，否则所有股票都被丢、雷达变空。"""
    from datetime import date

    from app.services.signal_radar import fundamental_top

    ranked = [(s, _qg("B", None)) for s in ("AAA", "BBB")]

    async def fake_ranked(market, universe, redis, end):
        return ranked, {}

    async def fake_scores(market, pairs):
        assert sorted(pairs) == [("AAA", date(2026, 10, 5)), ("BBB", date(2026, 10, 5))]
        return {("AAA", date(2026, 10, 5)): {"valuation": 90.0, "momentum": 5.0},
                ("BBB", date(2026, 10, 5)): {"valuation": 30.0, "momentum": 95.0}}

    class NoRedis:
        pass

    async def no_cache(*a, **k):
        return None

    monkeypatch.setattr(fundamental_top, "load_ranked", fake_ranked)
    monkeypatch.setattr(qv.repository, "get_dimension_scores", fake_scores)
    monkeypatch.setattr(qv, "get_json", no_cache)
    monkeypatch.setattr(qv, "set_json", no_cache)
    good, rated, _ = await qv.good_stocks("us", "sp500", NoRedis(), datetime(2026, 10, 6, tzinfo=UTC), qv.QUALITY_GOOD_XM)
    assert rated == 2 and "AAA" in good  # 动量 5 分不再拖累 AAA
