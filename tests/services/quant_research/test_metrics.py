"""指标注册表与报表口径计算（含特殊值）。"""

from dataclasses import replace

import pytest

from app.services.quant_research.inputs import fiscal_year_actual, ttm
from app.services.quant_research.metrics import DIMENSIONS, METRICS, compute_metrics
from tests.services.quant_research.fixtures import load_inputs


def test_registry_has_40_metrics_across_five_dimensions():
    assert len(METRICS) == 40
    assert {m.dimension for m in METRICS.values()} == set(DIMENSIONS)
    counts = {d: sum(m.dimension == d for m in METRICS.values()) for d in DIMENSIONS}
    assert counts == {"valuation": 14, "growth": 9, "profitability": 9, "momentum": 4, "revisions": 4}


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

