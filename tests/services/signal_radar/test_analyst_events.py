"""分析师评级 tab：券商评级变动 → 每只股票每天的净升降事件。"""
from datetime import date

from app.services.signal_radar import analyst_events as ae


def _a(d, firm, prev, new, action):
    return {"date": d, "firm": firm, "prev": prev, "new": new, "action": action}


def test_bucket_of_grade_names():
    assert ae.bucket_of("Overweight") == "buy"
    assert ae.bucket_of("Strong Buy") == "buy"
    assert ae.bucket_of("Market Outperform") == "buy"
    assert ae.bucket_of("Equal-Weight") == "hold"
    assert ae.bucket_of("Neutral") == "hold"
    assert ae.bucket_of("Underperform") == "sell"
    assert ae.bucket_of("Sell") == "sell"
    assert ae.bucket_of("") == "hold"


def test_net_up_down_per_day_and_window():
    history = {
        "AAA": [
            _a("2026-10-02", "X", "Hold", "Buy", "upgrade"),
            _a("2026-10-02", "Y", "Hold", "Outperform", "upgrade"),
            _a("2026-10-02", "Z", "Buy", "Hold", "downgrade"),
            _a("2026-10-02", "W", "Buy", "Buy", "maintain"),   # 维持不算
            _a("2026-09-01", "X", "Buy", "Hold", "downgrade"),  # 窗口外
        ],
        "BBB": [
            _a("2026-10-01", "X", "Buy", "Hold", "downgrade"),
            _a("2026-10-01", "Y", "Hold", "Sell", "downgrade"),
        ],
        "CCC": [  # 一升一降净 0：不画
            _a("2026-10-01", "X", "Hold", "Buy", "upgrade"),
            _a("2026-10-01", "Y", "Buy", "Hold", "downgrade"),
        ],
    }
    days = ae.build_events(history, {"AAA": "甲", "BBB": "乙"}, {"AAA": "科技"}, since=date(2026, 9, 25))
    assert [d.date for d in days] == ["2026-10-02", "2026-10-01"]
    d2 = days[0]
    assert (d2.up_count, d2.down_count) == (1, 0)
    e = d2.events[0]
    assert (e.symbol, e.direction, e.steps, e.upgrades, e.downgrades) == ("AAA", "up", 1, 2, 1)
    assert e.name == "甲" and e.sector == "科技" and e.to_bucket == "buy"
    d1 = days[1]
    assert [(x.symbol, x.direction, x.steps) for x in d1.events] == [("BBB", "down", 2)]
    assert d1.events[0].to_bucket == "sell"      # 取同方向最新（同日按列表顺序最后一条）的新评级归类


def test_events_sorted_by_steps_then_symbol():
    history = {
        "B": [_a("2026-10-02", "X", "Hold", "Buy", "upgrade")],
        "A": [_a("2026-10-02", "X", "Hold", "Buy", "upgrade")],
        "C": [_a("2026-10-02", "X", "Hold", "Buy", "upgrade"), _a("2026-10-02", "Y", "Hold", "Buy", "upgrade")],
    }
    days = ae.build_events(history, {}, {}, since=date(2026, 9, 25))
    assert [e.symbol for e in days[0].events] == ["C", "A", "B"]


def test_parse_actions_filters_and_trims():
    raw = [
        {"symbol": "A", "date": "2026-10-02", "gradingCompany": "X", "previousGrade": "Hold",
         "newGrade": "Buy", "action": "upgrade"},
        {"symbol": "A", "date": "2026-10-01", "gradingCompany": "Y", "previousGrade": "Buy",
         "newGrade": "Buy", "action": "maintain"},
        {"symbol": "A", "date": "bad", "action": "upgrade"},
    ]
    out = ae.parse_actions(raw)
    assert [x["action"] for x in out] == ["upgrade", "maintain"]
    assert out[0] == {"date": "2026-10-02", "firm": "X", "prev": "Hold", "new": "Buy", "action": "upgrade"}
    assert ae.parse_actions(None) == []


async def test_cn_hk_not_supported_and_unknown_universe():
    assert (await ae.analyst_events("cn", None, redis=None)).supported is False   # type: ignore[arg-type]
    assert (await ae.analyst_events("hk", "hstech", redis=None)).days == []       # type: ignore[arg-type]
    assert await ae.analyst_events("us", "nope", redis=None) is None              # type: ignore[arg-type]
