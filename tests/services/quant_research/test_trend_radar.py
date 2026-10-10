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
    assert out.counts["estimates"] == 3 and out.counts["quality"] == 1
    assert out.good_grade is None and not any(i.good for i in out.items)     # 没有评级：谁也不算达标
    assert out.thresholds["eps_up_7d"] == 0.02 and out.rings == [7, 30, 90]


def _est_row(symbol: str, grade: str | None, **eps) -> dict:
    return {"symbol": symbol, "grade": grade, "trend": TrendFacts(n_analysts=5, **eps).model_dump()}


def _pool(good_symbols: list[str]) -> list[dict]:
    """40 只有评级的股票：8 只 A（达标）、32 只 C。门槛 = 前 25% 且至少 8 只 → 取到 C 才够 → 被 B 的下限兜住，门槛 B。"""
    rows = [_est_row(s, "A", eps_rev_7d=0.05) for s in good_symbols]
    rows += [_est_row(f"X{k}", "A", eps_rev_7d=0.0) for k in range(8 - len(good_symbols))]
    rows += [_est_row(f"C{k}", "C", eps_rev_7d=0.0) for k in range(32)]
    return rows


def test_good_flag_uses_the_radar_quality_cutoff():
    rows = _pool(["G1", "G2"]) + [_est_row("LOW", "C", eps_rev_7d=0.06), _est_row("NOGRADE", None, eps_rev_7d=0.06)]
    out = build_trend_radar(rows, market="us", as_of=AS_OF)
    assert out.good_grade == "B"
    by = {i.symbol: i for i in out.items}
    assert by["G1"].good and by["G2"].good
    assert not by["LOW"].good and not by["NOGRADE"].good
    assert out.counts["estimates_good"] == 2


def test_magnitude_is_a_multiple_of_the_entry_threshold():
    rows = [_est_row("E7", "A", eps_rev_7d=0.05), _est_row("E30", "A", eps_rev_30d=0.10),
            {"symbol": "Q", "grade": "A", "trend": _q().model_dump()}]
    by = {i.symbol: i for i in build_trend_radar(rows, market="us", as_of=AS_OF).items}
    assert by["E7"].magnitude == 2.5          # 5% ÷ 7 天门槛 2%
    assert by["E30"].magnitude == 2.0         # 10% ÷ 30 天门槛 5%
    assert by["Q"].magnitude == 3.5           # 改善 3.5 个百分点 ÷ 利润率门槛 1 个百分点


def test_items_carry_the_radar_sector_key():
    rows = [_est_row("AAPL", "A", eps_rev_7d=0.05), _est_row("BRK.B", "A", eps_rev_7d=0.05), _est_row("ZZZ", "A", eps_rev_7d=0.05)]
    tags = {"AAPL": "technology", "BRK-B": "financials"}
    by = {i.symbol: i for i in build_trend_radar(rows, market="us", as_of=AS_OF, tags=tags).items}
    assert by["AAPL"].sector == "technology"
    assert by["BRK.B"].sector == "financials"          # 与雷达同一套代码规范化
    assert by["ZZZ"].sector is None


def test_good_items_are_kept_first_when_over_the_limit(monkeypatch):
    from app.services.quant_research import trend_radar

    monkeypatch.setattr(trend_radar, "PER_KIND_LIMIT", 2)
    rows = _pool(["G1", "G2", "G3"]) + [_est_row(f"L{k}", "C", eps_rev_7d=0.5 + k) for k in range(4)]
    out = build_trend_radar(rows, market="us", as_of=AS_OF)
    est = [i for i in out.items if i.kind == "estimates"]
    assert sum(i.good for i in est) == 2 and sum(not i.good for i in est) == 2    # 达标 ≤ 2、其余 ≤ 2，互不挤占


def test_filter_rows_keeps_only_pool_members():
    from app.services.quant_research.trend_radar import filter_rows

    rows = [{"symbol": "AAA"}, {"symbol": "BBB"}, {"symbol": "CCC"}]
    assert [r["symbol"] for r in filter_rows(rows, {"AAA", "CCC"})] == ["AAA", "CCC"]
    assert filter_rows(rows, None) == rows                    # 不限股票池：原样
    assert filter_rows(rows, set()) == []                      # 空池（自选里没有该市场的股票）：什么也不留


def test_good_cutoff_is_computed_inside_the_pool():
    """门槛按股票池自适应：同样是 B，放在 8 只全是 B 的小池子里仍然达标（门槛不会被全市场的分布拉高）。"""
    from app.services.quant_research.trend_radar import filter_rows

    market = _pool(["G1"]) + [_est_row(f"S{k}", "B", eps_rev_7d=0.05) for k in range(8)]
    small = filter_rows(market, {f"S{k}" for k in range(8)})
    out = build_trend_radar(small, market="us", as_of=AS_OF)
    assert out.good_grade == "B" and all(i.good for i in out.items)
