"""基本面动向事实：7 天预期变化（自有快照）、上一季对比（同一套指标往前挪一季）。"""

from dataclasses import replace
from datetime import timedelta

from app.services.quant_research.metrics import compute_metrics
from app.services.quant_research.revisions import EstimatePoint
from app.services.quant_research.trend import eps_week_change, trend_facts
from tests.services.quant_research.fixtures import load_inputs


def _history(inp, now_eps, old_eps, gap=7):
    fiscal = inp.fy1["date"]
    return [EstimatePoint(inp.as_of - timedelta(days=gap), fiscal, old_eps, None, 10),
            EstimatePoint(inp.as_of, fiscal, now_eps, None, 10)]


def test_week_change_from_own_snapshots():
    inp = load_inputs("NVDA")
    assert eps_week_change(inp, _history(inp, 4.4, 4.0)) == 0.1
    assert eps_week_change(inp, _history(inp, 4.4, 4.0, gap=20)) is None     # 7 天前附近没有快照
    assert eps_week_change(inp, []) is None


def test_quality_deltas_compare_with_previous_quarter():
    inp = load_inputs("NVDA")
    m = compute_metrics(inp)
    t = trend_facts(inp, [], m)
    prev = compute_metrics(replace(inp, quarters_income=inp.quarters_income[1:], quarters_cash=inp.quarters_cash[1:]))
    assert t.d_ebit_m_pp == round((m["ebit_m"].value - prev["ebit_m"].value) * 100, 2)
    assert t.quality_period == inp.quarters_income[0]["date"]
    assert t.quality_prev_period == inp.quarters_income[1]["date"]
    assert t.filing_date == inp.filing_date


def test_single_quarter_has_no_quality_deltas():
    inp = load_inputs("NVDA")
    one = replace(inp, quarters_income=inp.quarters_income[:1], quarters_cash=inp.quarters_cash[:1])
    t = trend_facts(one, [], compute_metrics(one))
    assert t.d_ebit_m_pp is None and t.quality_prev_period is None
