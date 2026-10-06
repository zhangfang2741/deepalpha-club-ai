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

    async def ok(market, universe, redis, now):
        return GOOD, 120, "B+"

    monkeypatch.setattr(qv, "good_stocks", ok)
    out = await qv.apply_quality(resp, None, now=now)    # type: ignore[arg-type]  # cn：不碰 analyst 缓存
    assert out.quality == "good" and out.quality_threshold == "B+"
    assert (out.quality_good_count, out.quality_rated_count) == (2, 120)
    assert [s.symbol for s in out.days[0].signals] == ["AAA"]

    async def broken(market, universe, redis, now):
        return None

    monkeypatch.setattr(qv, "good_stocks", broken)
    same = await qv.apply_quality(resp, None, now=now)   # type: ignore[arg-type]
    assert same is resp                                   # 评级读取失败：原样返回，雷达不能因此变空
