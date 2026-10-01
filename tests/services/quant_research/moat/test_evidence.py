"""护城河财务证据与评级合成（纯函数）。"""

import pytest

from app.services.quant_research.moat.evidence import compute_evidence
from app.services.quant_research.moat.rating import combine


def _years(vals):
    return [(2025 - i, v) for i, v in enumerate(vals)]  # 新 → 旧


def test_strong_evidence_needs_long_persistent_excess_returns():
    ev = compute_evidence(_years([0.20] * 10), beta=1.0, market_cap=100.0, total_debt=0.0)
    assert ev.level == "strong" and ev.years_above == 10 and ev.n_years == 10
    assert ev.wacc == pytest.approx(0.043 + 0.05)
    assert ev.avg_spread == pytest.approx(0.20 - 0.093)


def test_calibrated_threshold_three_points():
    """平均超额 3% 即算强证据（5% 会把 KO 这类老牌消费品判成窄）。"""
    ev = compute_evidence(_years([0.10] * 10), beta=0.4, market_cap=100.0, total_debt=0.0)
    assert ev.wacc == pytest.approx(0.063)  # 0.043 + 0.4 × 5% = 6.3%
    assert ev.level == "strong"


def test_weak_when_rarely_beats_cost_of_capital():
    ev = compute_evidence(_years([0.02, 0.05, 0.12, 0.01, 0.0, 0.03, 0.04, 0.02]), beta=1.2,
                          market_cap=50.0, total_debt=50.0)
    assert ev.level == "weak"


def test_trend_compares_recent_three_years_with_earliest_three():
    widening = compute_evidence(_years([0.30, 0.28, 0.26, 0.20, 0.18, 0.15, 0.14, 0.13]), beta=1.0,
                                market_cap=1.0, total_debt=0.0)
    assert widening.trend == "widening"
    stable = compute_evidence(_years([0.20] * 8), beta=1.0, market_cap=1.0, total_debt=0.0)
    assert stable.trend == "stable"
    short = compute_evidence(_years([0.20] * 4), beta=1.0, market_cap=1.0, total_debt=0.0)
    assert short.trend is None and short.level == "weak"


def test_wacc_blends_debt_and_is_clamped():
    ev = compute_evidence(_years([0.2] * 8), beta=3.0, market_cap=100.0, total_debt=0.0)
    assert ev.wacc == pytest.approx(0.14)  # 股权成本上限 14%
    ev2 = compute_evidence(_years([0.2] * 8), beta=1.0, market_cap=50.0, total_debt=50.0)
    assert ev2.wacc == pytest.approx(0.5 * 0.093 + 0.5 * (0.043 + 0.015) * (1 - 0.21))


def test_financials_compare_roe_with_cost_of_equity():
    ev = compute_evidence(_years([0.15] * 10), beta=1.0, market_cap=100.0, total_debt=900.0, financial=True)
    assert ev.metric == "roe" and ev.wacc == pytest.approx(0.093)  # 只看股权成本，不混入负债


@pytest.mark.parametrize("level, strengths, expected", [
    ("strong", ["strong", "none", "none", "none", "none"], "wide"),
    ("strong", ["moderate", "moderate", "none", "none", "none"], "wide"),
    ("strong", ["moderate", "weak", "none", "none", "none"], "narrow"),
    ("moderate", ["strong", "strong", "none", "none", "none"], "narrow"),
    ("moderate", ["weak", "weak", "weak", "none", "none"], "none"),
    ("weak", ["strong", "strong", "strong", "none", "none"], "none"),  # 来源再强，财务不支持也不算
])
def test_rating_needs_both_evidence_and_sources(level, strengths, expected):
    assert combine(level, strengths) == expected
