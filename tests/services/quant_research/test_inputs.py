"""报表 TTM、财年实际值、NTM 预期解析。"""

from datetime import date

from app.services.quant_research.inputs import (
    analyst_count,
    fiscal_year_actual,
    forward_entries,
    ntm,
    ttm,
)
from tests.services.quant_research.fixtures import AS_OF, load_inputs, raw


def _q(fy, period, revenue, d):
    return {"fiscalYear": fy, "period": period, "revenue": revenue, "date": d}


def test_ttm_sums_four_quarters_and_offsets():
    qs = [_q("2027", "Q2", 40, "2026-07"), _q("2027", "Q1", 30, "2026-04"), _q("2026", "Q4", 20, "2026-01"),
          _q("2026", "Q3", 10, "2025-10"), _q("2026", "Q2", 5, "2025-07")]
    assert ttm(qs, "revenue") == 100
    assert ttm(qs, "revenue", 1) == 65
    assert ttm(qs, "revenue", 2) is None  # 不足 4 季


def test_ttm_missing_value_returns_none():
    qs = [_q("2027", "Q2", None, "a")] + [_q("2027", "Q1", 1, "b")] * 3
    assert ttm(qs, "revenue") is None


def test_fiscal_year_actual_picks_latest_complete_year():
    qs = [_q("2027", "Q2", 40, "2026-07"), _q("2027", "Q1", 30, "2026-04"),
          _q("2026", "Q4", 4, "2026-01"), _q("2026", "Q3", 3, "2025-10"),
          _q("2026", "Q2", 2, "2025-07"), _q("2026", "Q1", 1, "2025-04")]
    assert fiscal_year_actual(qs, "revenue") == ("2026", 10)


def test_nvda_fiscal_year_actual_is_fy2026():
    inp = load_inputs("NVDA")
    fy, rev = fiscal_year_actual(inp.quarters_income, "revenue")
    assert fy == "2026"
    assert rev > 1e11


def test_forward_entries_and_ntm_weighting():
    est = [{"date": "2026-01-25", "epsAvg": 4.0}, {"date": "2027-01-25", "epsAvg": 5.0},
           {"date": "2028-01-25", "epsAvg": 8.0}]
    fy1, fy2 = forward_entries(est, date(2026, 9, 30))
    assert fy1["date"] == "2027-01-25" and fy2["date"] == "2028-01-25"
    # FY1 剩 117 天 → 权重 117/365
    w = (date(2027, 1, 25) - date(2026, 9, 30)).days / 365
    assert abs(ntm(fy1, fy2, "epsAvg", date(2026, 9, 30)) - (w * 5 + (1 - w) * 8)) < 1e-9
    assert ntm(fy1, None, "epsAvg", date(2026, 9, 30)) == 5.0
    assert ntm(None, None, "epsAvg", date(2026, 9, 30)) is None


def test_analyst_count():
    assert analyst_count({"numAnalystsEps": 12}) == 12
    assert analyst_count({}) == 0
    assert analyst_count(None) == 0


def test_build_inputs_nvda():
    inp = load_inputs("NVDA")
    assert inp.price is not None and inp.price > 0
    assert len(inp.closes) > 252  # 够算 12 个月动量
    assert inp.fiscal_period == "FY27 Q2"
    assert inp.quarters_income[0]["date"] > inp.quarters_income[1]["date"]
    assert inp.estimates[0]["date"] < inp.estimates[-1]["date"]
    assert inp.shares_diluted and inp.shares_diluted > 1e9
    assert inp.balance and inp.balance["totalAssets"] > 0
    assert inp.as_of == AS_OF
    assert inp.price_date == max(p["date"] for p in raw("NVDA", "px"))


def test_build_inputs_uses_operating_income_for_ebit_and_ebitda():
    """FMP 的 ebit / ebitda 含营业外收益（WDC 一年约 54.5 亿，占 EBIT 的一半以上）：改用经营利润口径，与分析师预期的 EBIT 同口径。"""
    from datetime import date

    from app.services.quant_research.inputs import build_inputs

    row = {"date": "2026-07-03", "operatingIncome": 4_453e6, "depreciationAndAmortization": 375e6,
           "ebit": 9_905e6, "ebitda": 10_280e6}
    no_oi = {"date": "2026-04-03", "ebit": 100.0, "ebitda": 120.0, "depreciationAndAmortization": 20.0}   # A 股 / 港股行没有 operatingIncome
    inp = build_inputs(symbol="WDC", as_of=date(2026, 10, 10), sector_key="information_technology",
                       income=[row, no_oi], cash=None, balance=None, estimates=None, prices=None)
    first, second = inp.quarters_income
    assert first["ebit"] == 4_453e6 and first["ebitda"] == 4_453e6 + 375e6
    assert second["ebit"] == 100.0 and second["ebitda"] == 120.0           # 没有经营利润字段的行不动
    assert row["ebit"] == 9_905e6                                          # 不改调用方传入的原始数据
