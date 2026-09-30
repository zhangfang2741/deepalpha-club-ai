"""分析师评级概览整理层（NVDA 2026-09-30 真实响应）。"""

import json
from datetime import date
from pathlib import Path

from app.services.analyst_upgrade.overview import build_overview, build_ratings, grade_label, unsupported
from app.services.quant_research.copy import contains_forbidden

F = Path(__file__).resolve().parents[2] / "fixtures" / "analyst_upgrade"
TODAY = date(2026, 9, 30)


def _raw(name):
    return json.loads((F / f"NVDA.{name}.json").read_text())


def _nvda(lang="zh"):
    return build_overview("NVDA", lang, TODAY, hist=_raw("hist"), ptc=_raw("ptc"), pts=_raw("pts"),
                          earnings=_raw("earnings"), grades=_raw("grades"), quote=_raw("quote"))


def test_ratings_from_grades_historical_only():
    o = _nvda()
    cur = o.ratings.current
    assert (cur.strong_buy, cur.buy, cur.hold, cur.sell, cur.strong_sell) == (11, 49, 2, 1, 0)
    assert cur.total == 63 and cur.date == "2026-09-01"
    assert o.ratings.history[0].date < o.ratings.history[-1].date
    assert o.ratings.change_text.startswith("近 3 个月：给出「买入」及以上评级的分析师")


def test_price_target_is_plain_arithmetic():
    t = _nvda().price_target
    assert (t.high, t.low, t.median, t.price) == (515, 270, 322.5, 227.21)
    assert t.vs_price_pct == round((322.5 / 227.21 - 1) * 100, 1)
    assert t.vs_price_text == f"目标价中位数较现价 +{t.vs_price_pct}%"
    assert t.last_year_count == 94


def test_earnings_quarters_and_next():
    e = _nvda().earnings
    assert len(e.quarters) == 4 and e.quarters[-1].date == "2026-08-26"
    q = e.quarters[-1]
    assert q.surprise_pct == round((2.22 - 2.09) / 2.09 * 100, 1)
    assert e.next.date == "2026-11-18" and e.next.eps_estimated == 2.47


def test_recent_grades_labels():
    g = _nvda().recent_grades
    assert len(g) == 10 and g[0].date >= g[-1].date
    assert g[0].firm == "Rosenblatt" and g[0].action_label == "维持" and g[0].new_grade_label == "买入"
    assert grade_label("Overweight", "zh") == "增持"
    assert grade_label("Some New Label", "zh") == "Some New Label"
    assert grade_label("Buy", "en") == "Buy"


def test_our_own_copy_has_no_forbidden_words():
    """评级标签是引述原文（豁免）；我们自己生成的文案不得出现买卖导向措辞（「买入」只在引号里引用分析师评级档位）。"""
    for lang in ("zh", "en"):
        o = _nvda(lang)
        ours = [o.note, o.price_target.vs_price_text]
        assert all(contains_forbidden(t) == [] for t in ours), ours
        assert contains_forbidden(o.ratings.change_text.replace("「买入」", "").replace("Buy", "")) == []


def test_partial_and_empty():
    o = build_overview("X", "zh", TODAY, hist=_raw("hist"))
    assert o.status == "ok" and o.price_target is None and o.earnings is None
    e = build_overview("X", "zh", TODAY)
    assert e.status == "insufficient_data"
    assert unsupported("0700", "zh").status == "unsupported_market"


def test_change_text_directions():
    base = {"analystRatingsHold": 0, "analystRatingsSell": 0, "analystRatingsStrongSell": 0, "analystRatingsStrongBuy": 0}
    rows = [dict(base, date=f"2026-0{m}-01", analystRatingsBuy=b) for m, b in [(6, 10), (7, 9), (8, 9), (9, 8)]]
    assert build_ratings(rows, "zh").change_text.endswith("由 10 位减至 8 位")
    rows[-1]["analystRatingsBuy"] = 10
    assert "保持 10 位" in build_ratings(rows, "zh").change_text
