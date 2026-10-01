"""打分聚合：分布、百分位、维度分、综合等级与一票否决。"""

import pytest

from app.services.quant_research.metrics import MetricValue
from app.services.quant_research.scoring import (
    DimensionScore,
    ScoredMetric,
    build_distributions,
    composite,
    mark_extremes,
    overall,
    pick_key_fact,
    quantile,
    score_dimension,
    score_metric,
)

DIST = [float(i) for i in range(1, 101)]  # 1..100


def _mv(v, status="ok"):
    return MetricValue(v, status)


def test_build_distributions_only_ok_values():
    uni = {
        "A": ("tech", {"pe_ttm": _mv(10), "gross_m": _mv(None, "missing")}),
        "B": ("tech", {"pe_ttm": _mv(20), "gross_m": _mv(0.5)}),
        "C": ("energy", {"pe_ttm": _mv(None, "not_meaningful")}),
    }
    d = build_distributions(uni)
    assert d[("tech", "pe_ttm")] == [10.0, 20.0]
    assert d[("tech", "gross_m")] == [0.5]
    assert ("energy", "pe_ttm") not in d


def test_quantile_interpolates():
    assert quantile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5
    assert quantile([7.0], 0.9) == 7.0


def test_score_metric_lower_better_and_stats():
    s = score_metric("pe_ttm", _mv(10), DIST, None)
    assert s.percentile == 91.0
    assert s.grade == "A"
    assert s.sector_median == 50.5
    assert s.diff_to_median_pct == pytest.approx((10 - 50.5) / 50.5 * 100)
    assert s.distribution["p10"] == pytest.approx(10.9)


def test_score_metric_special_statuses():
    assert score_metric("pe_ttm", _mv(None, "not_meaningful"), DIST, None).percentile == 0.0
    assert score_metric("pe_ttm", _mv(None, "not_meaningful"), DIST, None).grade == "F"
    assert score_metric("pb", _mv(None, "not_applicable"), DIST, None).percentile is None
    assert score_metric("pb", _mv(None, "missing"), DIST, None).percentile is None
    small = score_metric("pe_ttm", _mv(10), DIST[:10], None)
    assert small.status == "insufficient_sample" and small.percentile is None


def _sm(key, p):
    return ScoredMetric(key, _mv(1), "ok", p, None, 100)


def test_dimension_average_and_unavailable():
    d = score_dimension("valuation", [_sm("pe_ttm", 12), _sm("pb", 71), _sm("pcf", None)], None)
    assert d.status == "ok" and d.score == 41.5 and d.grade == "C-"
    u = score_dimension("valuation", [_sm("pe_ttm", 12), _sm("pb", None), _sm("pcf", None)], None)
    assert u.status == "unavailable" and u.score is None   # 3 项只 1 项参与，不足 2 项
    # 9 项里 3 项参与（未盈利公司只剩营收增速）→ 仍给等级
    growth = [_sm("rev_yoy", 90), _sm("rev_fwd", 80), _sm("rev_cagr3", 70)] + [_sm("eps_yoy", None)] * 6
    assert score_dimension("growth", growth, None).status == "ok"
    assert score_dimension("growth", growth[1:], None).status == "unavailable"


def test_min_participating():
    from app.services.quant_research.scoring import min_participating
    assert [min_participating(n) for n in (1, 2, 3, 4, 9, 14)] == [1, 2, 2, 2, 3, 5]
    a = score_dimension("revisions", [], None, accumulating_days=12)
    assert a.status == "accumulating" and a.days_accumulated == 12


def _dim(key, score):
    return DimensionScore(key, "ok", score, None, [])


def test_overall_percentile_grade_and_cap():
    dims = [_dim("valuation", 15), _dim("growth", 95), _dim("profitability", 95), _dim("momentum", 95)]
    # 综合分 75，放进 0..100 的分布里约第 76 百分位 → B+，但估值 < 20 → 封顶 C+
    o = overall(dims, DIST, n_analysts=10, prev_grade=None)
    assert o.score == 75.0
    assert o.grade == "C+" and o.capped and o.cap_dimension == "valuation"
    assert o.dimensions_used == 4


def test_overall_no_cap_when_already_low():
    dims = [_dim("valuation", 15), _dim("growth", 20), _dim("profitability", 20)]
    o = overall(dims, DIST, n_analysts=10, prev_grade=None)
    assert o.grade == "F" and o.capped is False


def test_overall_few_analysts_no_grade():
    o = overall([_dim("growth", 80)], DIST, n_analysts=2, prev_grade=None)
    assert o.grade is None and o.score == 80.0 and o.extra["reason"] == "few_analysts"


def test_key_fact_and_extremes():
    high = score_dimension("growth", [_sm("rev_yoy", 99), _sm("eps_yoy", 60)], None)
    assert pick_key_fact(high) == "rev_yoy"
    low = score_dimension("valuation", [_sm("pe_ttm", 12), _sm("pb", 4)], None)
    assert pick_key_fact(low) == "pb"
    dims = [low, high, _dim("momentum", 74)]
    mark_extremes(dims)
    assert high.is_highest and low.is_lowest
    assert not dims[2].is_highest and not dims[2].is_lowest


def test_display_only_dimension_never_moves_the_composite(monkeypatch):
    """只展示的维度：不进综合分、不算「基于 N 个维度」、F 也不触发封顶（机制保留，目前没有维度使用）。"""
    from app.services.quant_research import scoring

    monkeypatch.setattr(scoring, "DISPLAY_ONLY_DIMENSIONS", frozenset({"moat"}))
    base = [_dim("growth", 80), _dim("valuation", 60)]
    with_moat = base + [_dim("moat", 5)]
    assert composite(with_moat) == composite(base)
    o = overall(with_moat, DIST, n_analysts=10, prev_grade=None)
    o_base = overall(base, DIST, n_analysts=10, prev_grade=None)
    assert (o.score, o.grade, o.dimensions_used, o.capped) == (o_base.score, o_base.grade, 2, False)
