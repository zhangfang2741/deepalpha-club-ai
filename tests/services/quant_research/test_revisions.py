"""EPS 修正：变化率、回看、积累期。"""

from datetime import date, timedelta

import pytest

from app.services.quant_research.revisions import (
    EstimatePoint,
    change,
    compute_revisions,
    revision_status,
    value_at,
)

AS_OF = date(2026, 12, 31)
FY1, FY2 = "2027-01-25", "2028-01-25"


def _series(days: int, start_eps: float, end_eps: float, fiscal=FY1):
    pts = []
    for i in range(days + 1):
        d = AS_OF - timedelta(days=days - i)
        eps = start_eps + (end_eps - start_eps) * i / days
        pts.append(EstimatePoint(d, fiscal, eps, 100 + i, 12))
    return pts


def test_change_uses_abs_base_so_narrowing_loss_is_positive():
    assert change(-0.8, -1.0) == pytest.approx(0.2)
    assert change(5.5, 5.0) == pytest.approx(0.1)
    assert change(1.0, 0) is None
    assert change(None, 1.0) is None


def test_value_at_respects_tolerance():
    pts = [EstimatePoint(date(2026, 1, 1), FY1, 1.0, None)]
    assert value_at(pts, FY1, date(2026, 1, 5), "eps_avg") == 1.0
    assert value_at(pts, FY1, date(2026, 1, 20), "eps_avg") is None
    assert value_at(pts, FY2, date(2026, 1, 5), "eps_avg") is None


def test_full_history_computes_all_four():
    hist = _series(100, 5.0, 5.5) + _series(100, 8.0, 8.8, fiscal=FY2)
    r = compute_revisions(hist, AS_OF, FY1, FY2, n_analysts=12)
    assert all(v.status == "ok" for v in r.values())
    eps_90d_ago = 5.0 + 0.5 * 10 / 100
    assert r["eps_fy1_90d"].value == pytest.approx((5.5 - eps_90d_ago) / eps_90d_ago)
    assert r["eps_fy2_90d"].value > 0
    assert r["rev_fy1_90d"].value == pytest.approx((200 - 110) / 110)


def test_partial_history_only_30d():
    hist = _series(45, 5.0, 5.2)
    r = compute_revisions(hist, AS_OF, FY1, FY2, n_analysts=12)
    assert r["eps_fy1_30d"].status == "ok"
    assert r["eps_fy1_90d"].status == "missing"
    assert revision_status(hist, AS_OF) == ("ok", 45)


def test_accumulating_status():
    hist = _series(10, 5.0, 5.1)
    assert revision_status(hist, AS_OF) == ("accumulating", 10)
    assert revision_status([], AS_OF) == ("accumulating", 0)


def test_few_analysts_missing():
    r = compute_revisions(_series(100, 5.0, 5.5), AS_OF, FY1, FY2, n_analysts=2)
    assert all(v.status == "missing" for v in r.values())


# ---------- 过渡期：自有快照不满回看天数时用外部一致预期趋势 ----------

from app.services.quant_research.revisions import EpsTrend  # noqa: E402

TREND = EpsTrend(fy1={0: 9.31, 30: 9.29, 90: 8.94}, fy2={0: 15.68, 30: 15.31, 90: 12.71})


def test_trend_bridges_eps_revisions_while_history_is_short():
    hist = _series(1, 9.3, 9.3)  # 自有快照只有 1 天
    out = compute_revisions(hist, AS_OF, FY1, FY2, 20, trend=TREND, fy1_eps=9.3, fy2_eps=15.7)
    assert out["eps_fy1_30d"].status == "ok"
    assert out["eps_fy1_30d"].value == pytest.approx(9.31 / 9.29 - 1)
    assert out["eps_fy1_90d"].value == pytest.approx(9.31 / 8.94 - 1)
    assert out["eps_fy2_90d"].value == pytest.approx(15.68 / 12.71 - 1)
    assert out["eps_fy1_30d"].meta["source"] == "trend"
    # 营收没有外部趋势，仍需自有快照攒满 90 天
    assert out["rev_fy1_90d"].status == "missing"


def test_own_history_takes_over_once_long_enough():
    hist = _series(95, 5.0, 5.5)
    out = compute_revisions(hist, AS_OF, FY1, FY2, 20, trend=TREND, fy1_eps=5.5, fy2_eps=None)
    assert out["eps_fy1_90d"].meta.get("source") != "trend"
    assert out["eps_fy1_90d"].value == pytest.approx(5.5 / (5.0 + 0.5 * 5 / 95) - 1, rel=1e-3)


def test_trend_skipped_when_fiscal_year_does_not_line_up():
    """外部「本财年」与我们的 FY1 预期差太多，说明财年口径没对齐（如刚跨财年），宁缺不用。"""
    out = compute_revisions([], AS_OF, FY1, FY2, 20, trend=TREND, fy1_eps=15.7, fy2_eps=15.7)
    assert out["eps_fy1_30d"].status == "missing"
    assert out["eps_fy2_90d"].status == "ok"


def test_trend_respects_min_analysts():
    out = compute_revisions([], AS_OF, FY1, FY2, 2, trend=TREND, fy1_eps=9.3, fy2_eps=15.7)
    assert all(v.status == "missing" for v in out.values())
