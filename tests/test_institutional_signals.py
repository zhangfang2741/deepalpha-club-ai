"""机构资金信号——维度打分与状态引擎单元测试（纯函数，无网络）。"""

import datetime
from typing import Any, cast

import pytest

from app.services.institutional_signals.dimensions import (
    compute_confirmation,
    compute_expectation,
    compute_fundamental,
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

def test_expectation_signal_has_full_explanation():
    pt = {"lastMonthAvgPriceTarget": 120, "lastQuarterAvgPriceTarget": 100, "lastMonthCount": 8}
    dim = compute_expectation(pt, [])
    tp = next(s for s in dim.signals if s.key == "target_price")
    assert tp.explain is not None
    assert tp.explain.inputs and tp.explain.formula and tp.explain.conclusion
    assert tp.explain.source == "FMP price-target-summary"
    # 原始数据里应能看到近月/近季均值
    assert any("120" in x for x in tp.explain.inputs)


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


def test_expectation_no_data_is_unavailable():
    dim = compute_expectation(None, [])
    assert dim.status == "unavailable"


def test_expectation_low_analyst_count_ignored():
    pt = {"lastMonthAvgPriceTarget": 120, "lastQuarterAvgPriceTarget": 100, "lastMonthCount": 1}
    dim = compute_expectation(pt, [])
    # 样本不足 + 无评级 → 无有效数据
    assert dim.status == "unavailable"


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


# ── Fundamental ─────────────────────────────────────────────────────────────

def _earn(date, eps_a, eps_e, rev_a=None, rev_e=None) -> dict:
    return {"date": date, "epsActual": eps_a, "epsEstimated": eps_e,
            "revenueActual": rev_a, "revenueEstimated": rev_e}


def test_fundamental_consecutive_beats_and_revenue():
    earnings = [
        _earn("2026-04-01", 2.1, 1.9, 100e9, 96e9),
        _earn("2026-01-01", 2.0, 1.8),
        _earn("2025-10-01", 1.9, 1.7),
        _earn("2025-07-01", 1.6, 1.5),
    ]
    dim = compute_fundamental(earnings)
    assert dim.status == "ok"
    assert dim.score >= 70
    assert any(s.key == "earnings_surprise" and s.hit and s.direction == "up" for s in dim.signals)
    assert any(s.key == "revenue_surprise" and s.hit and s.direction == "up" for s in dim.signals)


def test_fundamental_recent_miss_scores_low():
    earnings = [_earn("2026-04-01", 1.5, 1.9, 90e9, 96e9)]
    dim = compute_fundamental(earnings)
    assert dim.score < 50
    assert any(s.key == "earnings_surprise" and s.direction == "down" for s in dim.signals)


def test_fundamental_no_data_is_unavailable():
    assert compute_fundamental([]).status == "unavailable"


def test_fundamental_earnings_window():
    soon = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
    earnings = [_earn("2026-01-01", 2.0, 1.8), {"date": soon, "epsActual": None, "epsEstimated": 2.2}]
    dim = compute_fundamental(earnings)
    assert any(s.key == "earnings_date" and s.hit for s in dim.signals)


# ── Confirmation ────────────────────────────────────────────────────────────

def test_confirmation_open_market_purchase():
    stats = [
        {"year": 2026, "quarter": 2, "acquiredDisposedRatio": 1.5, "totalPurchases": 3, "totalSales": 0},
        {"year": 2026, "quarter": 1, "acquiredDisposedRatio": 1.2, "totalPurchases": 1, "totalSales": 0},
    ]
    dim = compute_confirmation(stats)
    assert dim.status == "ok"
    assert dim.score >= 65
    assert any(s.key == "insider" and s.hit and s.direction == "up" for s in dim.signals)


def test_confirmation_concentrated_selling():
    stats = [
        {"year": 2026, "quarter": 2, "acquiredDisposedRatio": 0.15, "totalPurchases": 0, "totalSales": 20},
        {"year": 2026, "quarter": 1, "acquiredDisposedRatio": 0.2, "totalPurchases": 0, "totalSales": 15},
    ]
    dim = compute_confirmation(stats)
    assert dim.score < 50
    assert any(s.key == "insider" and s.hit and s.direction == "down" for s in dim.signals)


def test_confirmation_no_data_is_unavailable():
    assert compute_confirmation([]).status == "unavailable"


# ── 快照衍生的变化率（纯函数）────────────────────────────────────────────────

def test_deltas_pct_change():
    from app.services.institutional_signals.deltas import pct_change
    assert pct_change(110, 100) == 10.0
    assert pct_change(90, 100) == -10.0
    assert pct_change(100, 0) is None
    assert pct_change(None, 100) is None


def test_deltas_iv_rank():
    from app.services.institutional_signals.deltas import iv_rank
    hist = [0.2 + i * 0.01 for i in range(30)]  # 0.20 → 0.49
    assert iv_rank(0.49, hist) == 100.0
    assert iv_rank(0.20, hist) == 0.0
    assert iv_rank(0.35, hist) is not None
    assert iv_rank(0.4, hist[:5]) is None  # 历史点不足


def test_deltas_value_days_ago():
    import datetime
    from app.services.institutional_signals.deltas import value_days_ago
    d90 = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
    d5 = (datetime.date.today() - datetime.timedelta(days=200)).isoformat()
    pts = [(d90, 5.0), (d5, 9.0)]
    assert value_days_ago(pts, 90) == 5.0
    assert value_days_ago(pts, 90, tolerance=3) == 5.0
    assert value_days_ago([(d5, 9.0)], 90) is None  # 超出容差


# ── 维度升级：有快照历史时用变化率 ───────────────────────────────────────────

def test_positioning_uses_iv_rank_and_oi_change():
    metrics = {"call_vol": 50000, "put_vol": 20000, "call_oi": 80000, "put_oi": 40000, "atm_iv": 0.5}
    dim = compute_positioning(metrics, iv_rank_value=85, oi_change_pct=15)
    iv = next(s for s in dim.signals if s.key == "iv_level")
    assert "Rank" in (iv.value or "") and iv.hit
    oi = next(s for s in dim.signals if s.key == "oi_change")
    assert oi.hit and oi.direction == "up"


def test_expectation_uses_eps_revision():
    pt = {"lastMonthAvgPriceTarget": 120, "lastQuarterAvgPriceTarget": 100, "lastMonthCount": 8}
    dim = compute_expectation(pt, [], eps_revision_pct=3.5, revenue_revision_pct=2.0)
    eps = next(s for s in dim.signals if s.key == "eps_revision")
    assert eps.hit and eps.direction == "up" and eps.value == "+3.5%"


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


def test_states_carry_buy_meta():
    pt = {"lastMonthAvgPriceTarget": 120, "lastQuarterAvgPriceTarget": 100, "lastMonthCount": 8}
    grades = [
        {"date": "2026-06-01", "analystRatingsStrongBuy": 10, "analystRatingsBuy": 5,
         "analystRatingsHold": 3, "analystRatingsSell": 1, "analystRatingsStrongSell": 0},
        {"date": "2026-05-01", "analystRatingsStrongBuy": 5, "analystRatingsBuy": 5,
         "analystRatingsHold": 8, "analystRatingsSell": 2, "analystRatingsStrongSell": 0},
    ]
    exp = compute_expectation(pt, grades)
    states = derive_states({"expectation": exp})
    up = next(s for s in states if s.key == "expectation_upgrade")
    assert up.buy_rank == 4 and up.buy_timing and up.buy_edge and up.buy_thesis


def test_build_buy_view_ladder():
    from app.services.institutional_signals.calculator import _build_buy_view
    from app.schemas.institutional_signals import SignalState
    st = SignalState(key="institution_accumulation", emoji="🔥", label="机构建仓", stars=5,
                     meaning="", evidence=[], buy_rank=2, buy_timing="早中段",
                     buy_edge="胜率最高", buy_thesis="多维印证")
    headline, ladder = _build_buy_view([st])
    assert len(ladder) == 5
    assert [r.active for r in ladder] == [False, True, False, False, False]
    assert "机构建仓" in headline and "胜率最高" in headline


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


def test_rank_prefers_bullish_state_then_score():
    from app.schemas.institutional_signals import LeaderboardEntry, SignalState
    from app.services.institutional_signals.scan import _rank

    strong = SignalState(key="institution_accumulation", emoji="🔥", label="机构建仓",
                         stars=5, meaning="", evidence=[])
    a = LeaderboardEntry(symbol="A", name="A", composite_score=60, coverage=4,
                         confidence="高", top_state=None)
    b = LeaderboardEntry(symbol="B", name="B", composite_score=55, coverage=4,
                         confidence="高", top_state=strong)
    c = LeaderboardEntry(symbol="C", name="C", composite_score=70, coverage=4,
                         confidence="高", top_state=None)
    ranked = _rank([a, b, c])
    # 有偏多状态的 B 最前；其余按综合分 C > A
    assert [e.symbol for e in ranked] == ["B", "C", "A"]


def test_states_smart_money_price_not_moved():
    # 预期背书 + 期权看涨下注 + 高 IV，但价格未突破（平稳窄幅）
    pt = {"lastMonthAvgPriceTarget": 120, "lastQuarterAvgPriceTarget": 100, "lastMonthCount": 8}
    exp = compute_expectation(pt, [])
    pos = compute_positioning(
        {"call_vol": 50000, "put_vol": 20000, "call_oi": 80000, "put_oi": 40000, "atm_iv": 0.72})
    par = compute_participation(_make_prices(25))  # 无突破
    states = derive_states({"expectation": exp, "positioning": pos, "participation": par})
    keys = {s.key for s in states}
    assert "smart_money" in keys


def test_states_smart_money_and_event_trading_mutually_exclusive():
    """无预期背书时只应触发热钱（投机），不应误判为聪明钱。"""
    pos = compute_positioning(
        {"call_vol": 50000, "put_vol": 20000, "call_oi": 80000, "put_oi": 40000, "atm_iv": 0.72})
    par = compute_participation(_make_prices(25))  # 未突破
    states = derive_states({"positioning": pos, "participation": par})  # 无 expectation
    keys = {s.key for s in states}
    assert "event_trading" in keys and "smart_money" not in keys


def test_states_fundamental_turn():
    earnings = [
        _earn("2026-04-01", 2.1, 1.9, 100e9, 96e9),
        _earn("2026-01-01", 2.0, 1.8),
    ]
    fun = compute_fundamental(earnings)
    pt = {"lastMonthAvgPriceTarget": 120, "lastQuarterAvgPriceTarget": 100, "lastMonthCount": 8}
    exp = compute_expectation(pt, [])
    states = derive_states({"fundamental": fun, "expectation": exp})
    assert "fundamental_turn" in {s.key for s in states}


def test_states_distribution():
    grades = [
        {"date": "2026-06-01", "analystRatingsStrongBuy": 2, "analystRatingsBuy": 3,
         "analystRatingsHold": 8, "analystRatingsSell": 5, "analystRatingsStrongSell": 2},
        {"date": "2026-05-01", "analystRatingsStrongBuy": 8, "analystRatingsBuy": 6,
         "analystRatingsHold": 4, "analystRatingsSell": 1, "analystRatingsStrongSell": 0},
    ]
    exp = compute_expectation(None, grades)
    stats = [
        {"year": 2026, "quarter": 2, "acquiredDisposedRatio": 0.15, "totalPurchases": 0, "totalSales": 20},
        {"year": 2026, "quarter": 1, "acquiredDisposedRatio": 0.2, "totalPurchases": 0, "totalSales": 15},
    ]
    con = compute_confirmation(stats)
    states = derive_states({"expectation": exp, "confirmation": con})
    assert "distribution" in {s.key for s in states}


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data

    def json(self):
        return self._json_data


class _FakeWikiClient:
    def __init__(self, html: str, api_page: str):
        self.html = html
        self.api_page = api_page
        self.urls: list[str] = []

    async def get(self, url: str, **kwargs):
        self.urls.append(url)
        if "financialmodelingprep.com" in url:
            return _FakeResponse(200, json_data=[])
        if "w/api.php" in url and self.api_page in url:
            return _FakeResponse(200, json_data={"parse": {"text": self.html}})
        return _FakeResponse(403)


def _wiki_table_html(symbols: list[str]) -> str:
    rows = "".join(
        f"<tr><td>{sym}</td><td>{sym} Inc.</td><td>Technology</td></tr>"
        for sym in symbols
    )
    return (
        "<table><thead><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


@pytest.mark.asyncio
async def test_fetch_sp500_symbols_uses_wikipedia_api_when_article_page_fails():
    from app.services.institutional_signals.fetchers import fetch_sp500_symbols

    symbols = ["AAPL", "MSFT", "NVDA"] + [f"AA{i}" for i in range(90)]
    client = _FakeWikiClient(_wiki_table_html(symbols), "List_of_S%26P_500_companies")

    result = await fetch_sp500_symbols(cast(Any, client))

    assert result[:3] == ["AAPL", "MSFT", "NVDA"]
    assert any("w/api.php" in url for url in client.urls)


@pytest.mark.asyncio
async def test_fetch_nasdaq100_symbols_uses_wikipedia_api_when_article_page_fails():
    from app.services.institutional_signals.fetchers import fetch_nasdaq100_symbols

    symbols = ["AAPL", "MSFT", "NVDA"] + [f"AB{i}" for i in range(90)]
    client = _FakeWikiClient(_wiki_table_html(symbols), "Nasdaq-100")

    result = await fetch_nasdaq100_symbols(cast(Any, client))

    assert result[:3] == ["AAPL", "MSFT", "NVDA"]
    assert any("w/api.php" in url for url in client.urls)


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
    acc = next(s for s in states if s.key == "institution_accumulation")
    assert "现货放量确认" in acc.evidence


def test_states_accumulation_fires_without_volume():
    """机构「提前」建仓不应被现货放量硬门槛卡住（悄悄吸筹本就不放量）。"""
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
    par = compute_participation(_make_prices(25))  # 平稳、无放量
    states = derive_states({"expectation": exp, "positioning": pos, "participation": par})
    acc = next((s for s in states if s.key == "institution_accumulation"), None)
    assert acc is not None and "现货放量确认" not in acc.evidence


@pytest.mark.asyncio
async def test_fetch_sp500_symbols_uses_csv_backup(monkeypatch):
    from app.services.institutional_signals import fetchers

    async def empty_get(_client, _path, _params):
        return []

    async def empty_wiki(_client, _universe):
        return []

    class Response:
        status_code = 200
        text = "Symbol,Security\nAAPL,Apple Inc.\nMSFT,Microsoft Corp.\nBRK.B,Berkshire Hathaway\n"

    class Client:
        async def get(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(fetchers, "_get", empty_get)
    monkeypatch.setattr(fetchers, "_fetch_wiki_symbols", empty_wiki)

    assert await fetchers.fetch_sp500_symbols(cast(Any, Client())) == ["AAPL", "MSFT"]
