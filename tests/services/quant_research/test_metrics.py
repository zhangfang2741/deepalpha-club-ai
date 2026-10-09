"""指标注册表与报表口径计算（含特殊值）。"""

from dataclasses import replace

import pytest

from app.services.quant_research.inputs import fiscal_year_actual, ttm
from app.services.quant_research.metrics import DIMENSIONS, METRICS, compute_metrics
from tests.services.quant_research.fixtures import load_inputs


def test_registry_has_45_metrics_across_six_dimensions():
    assert len(METRICS) == 45
    assert {m.dimension for m in METRICS.values()} == set(DIMENSIONS)
    counts = {d: sum(m.dimension == d for m in METRICS.values()) for d in DIMENSIONS}
    assert counts == {"valuation": 14, "growth": 9, "profitability": 9, "momentum": 4, "revisions": 4, "stability": 5}


def test_compute_returns_all_non_revision_metrics():
    m = compute_metrics(load_inputs("NVDA"))
    assert set(m) == {k for k, d in METRICS.items() if d.dimension != "revisions"}


def test_nvda_forward_pe_uses_price_over_ntm_eps():
    inp = load_inputs("NVDA")
    m = compute_metrics(inp)
    pe = m["pe_fwd"]
    assert pe.status == "ok"
    assert pe.inputs[0] == ("price", inp.price)
    assert pe.inputs[1][0] == "eps_ntm"
    assert pe.value == pytest.approx(inp.price / pe.inputs[1][1])
    assert pe.meta["n_analysts"] >= 3


def test_nvda_forward_revenue_growth_uses_last_full_fiscal_year():
    inp = load_inputs("NVDA")
    m = compute_metrics(inp)
    fy0 = fiscal_year_actual(inp.quarters_income, "revenue")[1]
    assert m["rev_fwd"].value == pytest.approx(inp.fy1["revenueAvg"] / fy0 - 1)
    assert m["rev_yoy"].value == pytest.approx(
        ttm(inp.quarters_income, "revenue") / ttm(inp.quarters_income, "revenue", 4) - 1)
    assert m["rev_yoy"].value > 0.3


def test_nvda_profitability_and_momentum_are_ok():
    m = compute_metrics(load_inputs("NVDA"))
    for k in ("gross_m", "ebit_m", "net_m", "fcf_m", "roe", "roa", "roic", "asset_turn", "r3m", "r12m"):
        assert m[k].status == "ok", k
    assert 0.5 < m["gross_m"].value < 0.9


def _with_quarter_override(inp, **fields):
    qs = [dict(q, **fields) for q in inp.quarters_income]
    return replace(inp, quarters_income=qs)


def test_loss_maker_pe_not_meaningful_and_growth_missing():
    inp = _with_quarter_override(load_inputs("NVDA"), epsDiluted=-0.5, ebit=-1e9, ebitda=-1e8)
    m = compute_metrics(inp)
    assert m["pe_ttm"].status == "not_meaningful"
    assert m["peg_ttm"].status == "not_meaningful"
    assert m["ev_ebit_ttm"].status == "not_meaningful"
    assert m["eps_yoy"].status == "missing"      # 基数为负，不算增速，也不按最差
    assert m["ebit_m"].status == "ok" and m["ebit_m"].value < 0


def test_negative_equity_is_not_applicable():
    inp = load_inputs("NVDA")
    inp = replace(inp, balance=dict(inp.balance, totalStockholdersEquity=-5e9))
    m = compute_metrics(inp)
    assert m["pb"].status == "not_applicable"
    assert m["roe"].status == "not_applicable"


def test_few_analysts_drop_forward_metrics():
    inp = load_inputs("NVDA")
    est = [dict(e, numAnalystsEps=2) for e in inp.estimates]
    m = compute_metrics(replace(inp, estimates=est))
    for k in ("pe_fwd", "peg_fwd", "ps_fwd", "ev_sales_fwd", "rev_fwd", "eps_fwd"):
        assert m[k].status == "missing", k
    assert m["pe_ttm"].status == "ok"


def test_short_price_history_missing_momentum():
    inp = replace(load_inputs("NVDA"), closes=[1.0] * 100)
    m = compute_metrics(inp)
    assert m["r3m"].status == "ok" and m["r6m"].status == "missing"


@pytest.mark.parametrize("sym", ["JPM", "O", "XOM"])
def test_other_fixtures_compute_without_errors(sym):
    m = compute_metrics(load_inputs(sym))
    assert sum(v.status == "ok" for v in m.values()) >= 25


def test_financials_forward_revenue_growth_not_applicable():
    m = compute_metrics(load_inputs("JPM"))
    assert m["rev_fwd"].status == "not_applicable"
    assert m["rev_fwd"].meta["reason"] == "financials_revenue_basis"



# ---------- 财务稳健 ----------

def _with(inp, *, balance=None, income=None, cash=None):
    """改一只样本股的最新资产负债表 / 各季利润表 / 各季现金流字段。"""
    kw = {}
    if balance is not None:
        kw["balance"] = dict(inp.balance, **balance)
    if income is not None:
        kw["quarters_income"] = [dict(q, **income) for q in inp.quarters_income]
    if cash is not None:
        kw["quarters_cash"] = [dict(q, **cash) for q in inp.quarters_cash]
    return replace(inp, **kw)


def test_stability_metrics_use_statement_values():
    inp = load_inputs("NVDA")
    m = compute_metrics(inp)
    bal = inp.balance
    cur = m["current_ratio"]
    assert cur.status == "ok"
    assert cur.value == pytest.approx(bal["totalCurrentAssets"] / bal["totalCurrentLiabilities"])
    assert [n for n, _ in cur.inputs] == ["current_assets", "current_liabilities"]
    cov = m["interest_cov"]
    assert cov.status == "ok"
    raw_cov = ttm(inp.quarters_income, "ebit") / abs(ttm(inp.quarters_income, "interestExpense"))
    assert raw_cov > 100 and cov.value == 100.0               # NVDA 约 497 倍，截到上限 100
    o_inp = load_inputs("O")                                   # 利息压力大的 REIT 不触顶
    o_cov = compute_metrics(o_inp)["interest_cov"]
    assert o_cov.value == pytest.approx(ttm(o_inp.quarters_income, "ebit") / abs(ttm(o_inp.quarters_income, "interestExpense")))
    assert o_cov.value < 100
    cfo = m["cfo_ni"]
    assert cfo.value == pytest.approx(ttm(inp.quarters_cash, "operatingCashFlow") / ttm(inp.quarters_income, "netIncome"))


def test_net_cash_company_has_zero_net_debt_ratio():
    """现金多过负债 = 净现金：比值记 0（最好），不是负数、也不是缺失。"""
    m = compute_metrics(_with(load_inputs("NVDA"), balance={"totalDebt": 10.0, "cashAndShortTermInvestments": 1e12}))
    nd = m["net_debt_ebitda"]
    assert nd.status == "ok" and nd.value == 0.0 and nd.meta["net_cash"] is True


def test_net_debt_with_negative_ebitda_is_not_meaningful():
    """有净负债而 EBITDA 为负：还不起的最差情形，按最差计。"""
    inp = _with(load_inputs("NVDA"), balance={"totalDebt": 1e12, "cashAndShortTermInvestments": 1.0},
                income={"ebitda": -1e9})
    assert compute_metrics(inp)["net_debt_ebitda"].status == "not_meaningful"


def test_net_debt_ratio_divides_by_ttm_ebitda():
    inp = _with(load_inputs("NVDA"), balance={"totalDebt": 100e9, "cashAndShortTermInvestments": 40e9})
    m = compute_metrics(inp)["net_debt_ebitda"]
    assert m.value == pytest.approx(60e9 / ttm(inp.quarters_income, "ebitda"))


def test_no_interest_expense_counts_as_best_coverage():
    m = compute_metrics(_with(load_inputs("NVDA"), income={"interestExpense": 0.0}))["interest_cov"]
    assert m.status == "ok" and m.value == 100.0 and m.meta["no_interest"] is True


def test_interest_coverage_is_capped():
    m = compute_metrics(_with(load_inputs("NVDA"), income={"interestExpense": 1.0}))["interest_cov"]
    assert m.value == 100.0


def test_runway_self_funding_vs_burning():
    inp = load_inputs("NVDA")
    ok = compute_metrics(inp)["runway_years"]
    assert ok.value == 10.0 and ok.meta["self_funding"] is True       # 自由现金流为正：不烧钱，记上限
    burn = _with(inp, balance={"cashAndShortTermInvestments": 24e9},
                 cash={"operatingCashFlow": -1.5e9, "capitalExpenditure": -1.5e9})   # 每季烧 3B → 年烧 12B
    r = compute_metrics(burn)["runway_years"]
    assert r.status == "ok" and r.value == pytest.approx(2.0) and "self_funding" not in r.meta


def test_runway_is_capped_at_ten_years():
    burn = _with(load_inputs("NVDA"), balance={"cashAndShortTermInvestments": 1e12},
                 cash={"operatingCashFlow": -1e6, "capitalExpenditure": -1e6})
    assert compute_metrics(burn)["runway_years"].value == 10.0


def test_cfo_to_net_income_not_applicable_when_loss():
    m = compute_metrics(_with(load_inputs("NVDA"), income={"netIncome": -1e9}))["cfo_ni"]
    assert m.status == "not_applicable" and m.value is None


def test_missing_balance_fields_are_missing_not_zero():
    """A 股 / 港股没有流动资产、利息：缺失而不是当成 0。"""
    inp = load_inputs("NVDA")
    bal = {k: v for k, v in inp.balance.items() if k not in ("totalCurrentAssets", "totalCurrentLiabilities")}
    m = compute_metrics(replace(inp, balance=bal))
    assert m["current_ratio"].status == "missing"
    inc = [{k: v for k, v in q.items() if k != "interestExpense"} for q in inp.quarters_income]
    assert compute_metrics(replace(inp, quarters_income=inc))["interest_cov"].status == "missing"


def test_financials_stability_not_applicable():
    m = compute_metrics(load_inputs("JPM"))
    for key in ("net_debt_ebitda", "interest_cov", "current_ratio", "runway_years", "cfo_ni"):
        assert m[key].status == "not_applicable", key
