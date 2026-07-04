"""机构资金信号——维度打分与状态引擎单元测试（纯函数，无网络）。"""

from app.services.institutional_signals.dimensions import (
    compute_expectation,
    compute_participation,
    compute_positioning,
    unavailable_dimension,
)
from app.services.institutional_signals.states import derive_states


def _make_prices(n: int, base_vol: float = 1_000_000, base_price: float = 100.0) -> list[dict]:
    """构造 n 天平稳日线（等量、窄幅），供各测试在末日改写。"""
    return [
        {"date": f"2026-06-{i + 1:02d}", "open": base_price, "high": base_price + 1,
         "low": base_price - 1, "close": base_price, "volume": base_vol}
        for i in range(n)
    ]


# ── Participation ───────────────────────────────────────────────────────────

def test_participation_insufficient_history_is_partial():
    dim = compute_participation(_make_prices(5))
    assert dim.status == "partial"
    assert dim.score == 50.0


def test_participation_high_volume_breakout_scores_high():
    prices = _make_prices(25)
    last = prices[-1]
    last["volume"] = 3_000_000          # 3x 放量
    last["open"] = 105.0                 # 高开
    last["close"] = 108.0               # 突破 20 日高点
    last["high"] = 108.0
    dim = compute_participation(prices)
    assert dim.status == "ok"
    assert dim.score >= 90
    assert any(s.key == "relative_volume" and s.hit for s in dim.signals)
    assert any(s.key == "breakout" and s.hit and s.direction == "up" for s in dim.signals)


def test_participation_quiet_range_scores_neutral_ish():
    dim = compute_participation(_make_prices(25))
    # 等量窄幅：相对量约 1.0、无跳空、无突破
    assert 45 <= dim.score <= 60
    assert not any(s.hit for s in dim.signals)


# ── Expectation ─────────────────────────────────────────────────────────────

def test_expectation_target_price_up_and_rating_up():
    pt = {"lastMonthAvgPriceTarget": 120, "lastQuarterAvgPriceTarget": 100, "lastMonthCount": 8}
    grades = [
        {"date": "2026-06-01", "analystRatingsStrongBuy": 10, "analystRatingsBuy": 5,
         "analystRatingsHold": 3, "analystRatingsSell": 1, "analystRatingsStrongSell": 0},
        {"date": "2026-05-01", "analystRatingsStrongBuy": 5, "analystRatingsBuy": 5,
         "analystRatingsHold": 8, "analystRatingsSell": 2, "analystRatingsStrongSell": 0},
    ]
    dim = compute_expectation(pt, grades)
    assert dim.status == "ok"
    assert dim.score >= 75
    assert any(s.key == "target_price" and s.hit and s.direction == "up" for s in dim.signals)
    assert any(s.key == "analyst_rating" and s.hit and s.direction == "up" for s in dim.signals)


def test_expectation_no_data_is_partial():
    dim = compute_expectation(None, [])
    assert dim.status == "partial"


def test_expectation_low_analyst_count_ignored():
    pt = {"lastMonthAvgPriceTarget": 120, "lastQuarterAvgPriceTarget": 100, "lastMonthCount": 1}
    dim = compute_expectation(pt, [])
    # 样本不足 + 无评级 → 无有效数据
    assert dim.status == "partial"


# ── Positioning ─────────────────────────────────────────────────────────────

def test_positioning_none_is_unavailable():
    dim = compute_positioning(None)
    assert dim.status == "unavailable"


def test_positioning_bullish_call_flow_high_iv():
    metrics = {"call_vol": 50000, "put_vol": 20000, "call_oi": 80000, "put_oi": 40000, "atm_iv": 0.72}
    dim = compute_positioning(metrics)
    assert dim.status == "ok"
    assert dim.score >= 70
    assert any(s.key == "call_flow" and s.hit and s.direction == "up" for s in dim.signals)
    assert any(s.key == "iv_level" and s.hit and s.direction == "up" for s in dim.signals)


def test_positioning_put_heavy_scores_low():
    metrics = {"call_vol": 10000, "put_vol": 20000, "call_oi": 30000, "put_oi": 60000, "atm_iv": 0.30}
    dim = compute_positioning(metrics)
    assert dim.status == "ok"
    assert dim.score <= 45
    assert any(s.key == "put_pressure" and s.hit and s.direction == "down" for s in dim.signals)


def test_positioning_no_volume_is_partial():
    dim = compute_positioning({"call_vol": 0, "put_vol": 0, "call_oi": 100, "put_oi": 100, "atm_iv": 0.3})
    assert dim.status == "partial"


# ── 状态引擎 ────────────────────────────────────────────────────────────────

def test_states_expectation_upgrade():
    pt = {"lastMonthAvgPriceTarget": 120, "lastQuarterAvgPriceTarget": 100, "lastMonthCount": 8}
    grades = [
        {"date": "2026-06-01", "analystRatingsStrongBuy": 10, "analystRatingsBuy": 5,
         "analystRatingsHold": 3, "analystRatingsSell": 1, "analystRatingsStrongSell": 0},
        {"date": "2026-05-01", "analystRatingsStrongBuy": 5, "analystRatingsBuy": 5,
         "analystRatingsHold": 8, "analystRatingsSell": 2, "analystRatingsStrongSell": 0},
    ]
    exp = compute_expectation(pt, grades)
    states = derive_states({"expectation": exp, "positioning": unavailable_dimension("positioning", "x")})
    keys = {s.key for s in states}
    assert "expectation_upgrade" in keys


def test_states_neutral_fallback():
    dims = {
        "expectation": compute_expectation(None, []),
        "participation": compute_participation(_make_prices(25)),
    }
    states = derive_states(dims)
    assert [s.key for s in states] == ["neutral"]


def test_states_breakout_confirmation():
    prices = _make_prices(25)
    prices[-1]["volume"] = 3_000_000
    prices[-1]["close"] = 108.0
    prices[-1]["high"] = 108.0
    par = compute_participation(prices)
    pt = {"lastMonthAvgPriceTarget": 120, "lastQuarterAvgPriceTarget": 100, "lastMonthCount": 8}
    exp = compute_expectation(pt, [])
    states = derive_states({"expectation": exp, "participation": par})
    assert "breakout_confirmation" in {s.key for s in states}


def test_states_smart_money_price_not_moved():
    # 期权看涨下注 + 高 IV，但价格未突破（平稳窄幅）
    pos = compute_positioning(
        {"call_vol": 50000, "put_vol": 20000, "call_oi": 80000, "put_oi": 40000, "atm_iv": 0.72})
    par = compute_participation(_make_prices(25))  # 无突破
    states = derive_states({"positioning": pos, "participation": par})
    assert "smart_money" in {s.key for s in states}


def test_states_institution_accumulation():
    # 预期强 + 期权看涨 + 高 IV + 现货放量
    pt = {"lastMonthAvgPriceTarget": 120, "lastQuarterAvgPriceTarget": 100, "lastMonthCount": 8}
    grades = [
        {"date": "2026-06-01", "analystRatingsStrongBuy": 10, "analystRatingsBuy": 5,
         "analystRatingsHold": 3, "analystRatingsSell": 1, "analystRatingsStrongSell": 0},
        {"date": "2026-05-01", "analystRatingsStrongBuy": 5, "analystRatingsBuy": 5,
         "analystRatingsHold": 8, "analystRatingsSell": 2, "analystRatingsStrongSell": 0},
    ]
    exp = compute_expectation(pt, grades)
    pos = compute_positioning(
        {"call_vol": 50000, "put_vol": 20000, "call_oi": 80000, "put_oi": 40000, "atm_iv": 0.72})
    prices = _make_prices(25)
    prices[-1]["volume"] = 3_000_000  # 放量
    par = compute_participation(prices)
    states = derive_states({"expectation": exp, "positioning": pos, "participation": par})
    assert "institution_accumulation" in {s.key for s in states}
