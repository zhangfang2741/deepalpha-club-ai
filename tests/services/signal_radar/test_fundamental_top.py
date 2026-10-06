"""基本面雷达：当前综合等级最高的前 N 只。"""
from datetime import date

from app.services.signal_radar import analyst_events as ae
from app.services.signal_radar import fundamental_top as ft
from app.services.signal_radar.quant_filter import QuantGrade


def _g(grade, score, as_of=date(2026, 10, 5), avail=None):
    return QuantGrade(grade, score, as_of, avail or as_of)


def test_rank_latest_uses_newest_row_then_grade_then_score():
    history = {
        "A": [_g("B", 50, date(2026, 10, 2)), _g("A+", 80, date(2026, 10, 5))],   # 取最新一行 A+
        "B": [_g("A+", 90)],
        "C": [_g("A", 70)],
        "D": [_g(None, None)],                                                   # 无等级丢弃
        "E": [_g("A+", 90)],
    }
    out = ft.rank_latest(history)
    assert [s for s, _ in out] == ["B", "E", "A", "C"]     # B/E 同分按代码；A(80)<90 排后；C 等级低


def test_rank_latest_same_day_later_write_wins():
    h = {"X": [_g("B", 50, avail=date(2026, 10, 5)), _g("A", 70, avail=date(2026, 10, 6))]}
    assert ft.rank_latest(h)[0][1].grade == "A"


def test_net_counts_window():
    acts = [
        {"date": "2026-10-02", "firm": "a", "prev": "", "new": "", "action": "upgrade"},
        {"date": "2026-10-01", "firm": "b", "prev": "", "new": "", "action": "upgrade"},
        {"date": "2026-09-01", "firm": "c", "prev": "", "new": "", "action": "downgrade"},   # 窗口外
        {"date": "2026-10-02", "firm": "d", "prev": "", "new": "", "action": "downgrade"},
    ]
    assert ae.net_counts(acts, date(2026, 9, 15)) == (2, 1)


async def test_unknown_universe_none():
    assert await ft.fundamental_top("us", "nope", redis=None) is None   # type: ignore[arg-type]
