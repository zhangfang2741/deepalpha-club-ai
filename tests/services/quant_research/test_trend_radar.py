"""基本面动向雷达：两类事实的入圈规则、排序与门槛回传。"""

from datetime import date

from app.schemas.quant_research import TrendFacts
from app.services.quant_research.trend_radar import build_trend_radar, estimates_item, quality_item

AS_OF = date(2026, 10, 9)


def test_estimates_ring_picks_shortest_window():
    assert estimates_item(TrendFacts(n_analysts=5, eps_rev_7d=0.03, eps_rev_30d=0.2)) == (7, 0.03)
    assert estimates_item(TrendFacts(n_analysts=5, eps_rev_7d=0.01, eps_rev_30d=0.06)) == (30, 0.06)
    assert estimates_item(TrendFacts(n_analysts=5, eps_rev_30d=0.04, eps_rev_90d=0.12)) == (90, 0.12)
    assert estimates_item(TrendFacts(n_analysts=5, eps_rev_90d=0.05)) is None
    assert estimates_item(TrendFacts(n_analysts=2, eps_rev_7d=0.5)) is None       # 分析师太少


def _q(filing="2026-10-05", **d):
    base = {"d_rev_yoy_pp": 1.0, "d_gross_m_pp": 0.5, "d_ebit_m_pp": 2.0, "d_fcf_m_pp": 0.0}
    return TrendFacts(filing_date=filing, **(base | d))


def test_quality_rules_and_ring_by_filing_age():
    assert quality_item(_q(), AS_OF) == (7, 3.5)
    assert quality_item(_q(filing="2026-09-20"), AS_OF)[0] == 30
    assert quality_item(_q(filing="2026-06-01"), AS_OF) is None                    # 超过 90 天
    assert quality_item(_q(d_ebit_m_pp=0.5, d_fcf_m_pp=0.5), AS_OF) is None          # 利润率提升不够
    assert quality_item(_q(d_rev_yoy_pp=-5.0), AS_OF) is None                        # 有一项明显变差
    assert quality_item(_q(d_rev_yoy_pp=0.0, d_gross_m_pp=0.0), AS_OF) is None       # 只有一项变好
    assert quality_item(TrendFacts(d_ebit_m_pp=3.0), AS_OF) is None                  # 没有披露日


def test_build_sorts_by_ring_then_strength_and_returns_thresholds():
    rows = [
        {"symbol": "A", "trend": TrendFacts(n_analysts=5, eps_rev_30d=0.08).model_dump()},
        {"symbol": "B", "trend": TrendFacts(n_analysts=5, eps_rev_7d=0.05).model_dump()},
        {"symbol": "C", "trend": TrendFacts(n_analysts=5, eps_rev_30d=0.20).model_dump()},
        {"symbol": "D", "trend": _q().model_dump()},
        {"symbol": "E", "trend": None},
    ]
    out = build_trend_radar(rows, market="us", as_of=AS_OF)
    est = [i.symbol for i in out.items if i.kind == "estimates"]
    assert est == ["B", "C", "A"]
    assert out.counts == {"estimates": 3, "quality": 1}
    assert out.thresholds["eps_up_7d"] == 0.02 and out.rings == [7, 30, 90]
