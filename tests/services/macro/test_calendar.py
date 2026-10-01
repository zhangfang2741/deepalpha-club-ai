"""宏观日历：白名单、时区换算、时间窗、去重、下一个重点事件。"""
from datetime import UTC, datetime

from app.services.macro.calendar import filter_events, next_key_event

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
RAW = [
    {"date": "2026-10-02 12:30:00", "country": "US", "event": "Non Farm Payrolls (Sep)", "impact": "High"},
    {"date": "2026-10-02 12:30:00", "country": "US", "event": "Nonfarm Payrolls Private (Sep)", "impact": "High"},
    {"date": "2026-10-01 14:00:00", "country": "US", "event": "ISM Manufacturing PMI (Sep)", "impact": "High"},
    {"date": "2026-10-07 18:00:00", "country": "US", "event": "Fed Interest Rate Decision", "impact": "High"},
    {"date": "2026-10-20 18:00:00", "country": "US", "event": "Fed Interest Rate Decision", "impact": "High"},
    {"date": "2026-09-30 12:30:00", "country": "US", "event": "Inflation Rate YoY (Aug)", "impact": "High"},
    {"date": "2026-10-03 01:30:00", "country": "CN", "event": "Inflation Rate YoY (Sep)", "impact": "High"},
    {"date": "bad", "country": "US", "event": "Unemployment Rate (Sep)", "impact": "High"},
]


def test_filters_whitelist_window_and_converts_to_new_york_time():
    """只留白名单、7 天内事件，时间换成美东。"""
    events = filter_events(RAW, "us", NOW)
    assert [e.name for e in events] == ["ISM 制造业 PMI", "非农就业", "美联储利率决议"]
    nfp = events[1]
    assert (nfp.date, nfp.time, nfp.importance) == ("2026-10-02", "08:30", 3)
    assert events[2].time == "14:00"


def test_english_names():
    """英文名。"""
    assert filter_events(RAW, "us", NOW, lang="en")[1].name == "Nonfarm Payrolls"


def test_other_markets_empty_in_phase_one():
    """第一期 A 股 / 港股没有日历。"""
    assert filter_events(RAW, "cn", NOW) == []


def test_next_key_event_skips_low_importance():
    """下一个重点事件跳过低重要度。"""
    events = filter_events(RAW, "us", NOW)
    assert next_key_event(events).name == "非农就业"
    assert next_key_event(events[:1]).name == "ISM 制造业 PMI"
    assert next_key_event([]) is None
