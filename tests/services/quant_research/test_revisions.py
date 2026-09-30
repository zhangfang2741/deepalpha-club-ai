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
