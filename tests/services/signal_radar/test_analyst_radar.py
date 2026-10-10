"""评级雷达（分析师评级）：券商评级变动 → 3 / 7 / 30 天窗口里的净上调 / 净下调，按圈、按幅度、按「好股票」整理。"""
from datetime import date

from app.services.signal_radar.analyst_radar import build_analyst_radar

AS_OF = date(2026, 10, 9)


def _a(d: str, firm: str, new: str, action: str, prev: str = "Hold") -> dict:
    return {"date": d, "firm": firm, "prev": prev, "new": new, "action": action}


def _build(history, grades=None, names=None, tags=None, pending=0):
    names = names or {s: s for s in history}
    return build_analyst_radar(history, names=names, grades=grades or {}, tags=tags or {}, as_of=AS_OF,
                               market="us", pending=pending)


def test_up_goes_to_the_smallest_window_with_a_net_upgrade():
    out = _build({
        "A": [_a("2026-10-07", "GS", "Buy", "upgrade")],                     # 2 天前 → 近 3 天
        "A2": [_a("2026-10-04", "GS", "Buy", "upgrade")],                    # 5 天前 → 近 1 周
        "B": [_a("2026-09-25", "MS", "Buy", "upgrade")],                     # 14 天前 → 近 1 月
        "C": [_a("2026-08-20", "JPM", "Buy", "upgrade")],                    # 50 天前 → 超出 30 天
    })
    by = {i.symbol: i for i in out.items}
    assert {k: v.ring_days for k, v in by.items()} == {"A": 3, "A2": 7, "B": 30}
    assert all(i.kind == "analyst_up" for i in out.items)
    assert by["A"].analyst.up == 1 and by["A"].analyst.down == 0 and by["A"].analyst.firms == ["GS"]
    assert by["A"].analyst.last_date == "2026-10-07" and by["A"].analyst.to_bucket == "buy"


def test_net_zero_is_not_an_event_and_net_down_is_the_green_side():
    out = _build({
        "FLAT": [_a("2026-10-07", "GS", "Buy", "upgrade"), _a("2026-10-06", "MS", "Sell", "downgrade", "Buy")],
        "DOWN": [_a("2026-10-08", "GS", "Sell", "downgrade", "Hold"), _a("2026-10-07", "MS", "Hold", "downgrade", "Buy")],
    })
    assert [i.symbol for i in out.items] == ["DOWN"]
    d = out.items[0]
    assert d.kind == "analyst_down" and d.strength == 2 and d.analyst.down == 2 and d.analyst.up == 0
    assert d.analyst.to_bucket == "sell"


def test_maintains_and_other_actions_are_ignored():
    out = _build({"A": [_a("2026-10-08", "GS", "Buy", "maintain"), _a("2026-10-08", "MS", "Buy", "reiterate")]})
    assert out.items == []


def test_a_stock_can_have_both_an_up_and_a_down_item():
    """近 1 周净下调、近 3 月整体净上调：两边各一条，方向各自成立。"""
    out = _build({"X": [_a("2026-10-08", "GS", "Sell", "downgrade", "Buy"),
                        _a("2026-09-20", "MS", "Buy", "upgrade"), _a("2026-09-15", "JPM", "Buy", "upgrade"),
                        _a("2026-09-12", "UBS", "Buy", "upgrade")]})
    kinds = {i.kind: i for i in out.items}
    assert kinds["analyst_down"].ring_days == 3
    assert kinds["analyst_up"].ring_days == 30        # 近 3 天 / 1 周窗口里净值 ≤ 0，到近 1 月才净 +2


def test_good_flag_uses_the_pool_cutoff_and_magnitude_is_net_count():
    grades = {"G": "A", "L": "C", **{f"P{k}": "C" for k in range(38)}, **{f"Q{k}": "A" for k in range(7)}}
    history = {"G": [_a("2026-10-08", "GS", "Buy", "upgrade"), _a("2026-10-07", "MS", "Buy", "upgrade")],
               "L": [_a("2026-10-08", "GS", "Buy", "upgrade")]}
    out = _build(history, grades=grades)
    by = {i.symbol: i for i in out.items}
    assert out.good_grade == "B"                       # 46 只有评级：前 25% = 12 只，8 只 A 不够 → 到 C 才够 → 被下限 B 兜住
    assert by["G"].good and not by["L"].good
    assert by["G"].magnitude > by["L"].magnitude and by["G"].strength == 2
    assert out.counts["analyst_up"] == 2 and out.counts["analyst_up_good"] == 1


def test_sorted_by_ring_then_strength_and_carries_names_sector_and_pending():
    history = {"A": [_a("2026-10-08", "GS", "Buy", "upgrade")],
               "B": [_a("2026-10-08", "GS", "Buy", "upgrade"), _a("2026-10-07", "MS", "Buy", "upgrade")]}
    out = _build(history, names={"A": "甲", "B": "乙"}, tags={"A": "technology"}, pending=7)
    assert [i.symbol for i in out.items] == ["B", "A"]            # 同一圈：净上调多的在前
    by = {i.symbol: i for i in out.items}
    assert by["A"].name == "甲" and by["A"].sector == "technology" and by["B"].sector is None
    assert out.pending_symbols == 7 and out.supported is True
    assert out.as_of == "2026-10-09" and out.rings == [3, 7, 30]


def test_unsupported_market_is_empty():
    out = build_analyst_radar({}, names={}, grades={}, tags={}, as_of=AS_OF, market="cn", pending=0, supported=False)
    assert out.supported is False and out.items == []
