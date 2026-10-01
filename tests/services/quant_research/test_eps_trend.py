"""外部 EPS 趋势：解析与过渡期接入评分。"""

from dataclasses import replace

import pandas as pd

from app.services.quant_research.builder import evaluate
from app.services.quant_research.eps_trend import needs_trend, parse_eps_trend
from app.services.quant_research.revisions import EpsTrend
from tests.services.quant_research.fixtures import load_inputs


def test_parse_eps_trend_maps_fiscal_years_and_lookbacks():
    df = pd.DataFrame(
        {"current": [2.47, 2.74, 9.31, 15.68], "7daysAgo": [2.47, 2.74, 9.31, 15.68],
         "30daysAgo": [2.47, 2.75, 9.29, 15.31], "60daysAgo": [2.34, 2.65, 8.95, 12.81],
         "90daysAgo": [2.34, 2.65, 8.94, float("nan")]},
        index=pd.Index(["0q", "+1q", "0y", "+1y"], name="period"))
    t = parse_eps_trend(df)
    assert t == EpsTrend(fy1={0: 9.31, 30: 9.29, 90: 8.94}, fy2={0: 15.68, 30: 15.31})


def test_parse_eps_trend_without_current_fy_is_none():
    assert parse_eps_trend(pd.DataFrame()) is None


def test_needs_trend_only_until_own_history_reaches_90_days():
    assert needs_trend(0) and needs_trend(89)
    assert not needs_trend(90)


def test_revisions_dimension_scores_during_bridge_period():
    inp = load_inputs("NVDA")
    fy1 = float(inp.fy1["epsAvg"])  # type: ignore[index]
    fy2 = float(inp.fy2["epsAvg"])  # type: ignore[index]
    trend = EpsTrend(fy1={0: fy1, 30: fy1 * 0.99, 90: fy1 * 0.95}, fy2={0: fy2, 30: fy2, 90: fy2 * 0.9})
    ev = evaluate(replace(inp, eps_trend=trend), [], {})
    rev = next(d for d in ev.dims if d.key == "revisions")
    assert rev.status != "accumulating"
    assert ev.metrics["eps_fy1_90d"].meta["source"] == "trend"
    # 没有外部趋势时仍是积累中
    ev2 = evaluate(inp, [], {})
    assert next(d for d in ev2.dims if d.key == "revisions").status == "accumulating"
