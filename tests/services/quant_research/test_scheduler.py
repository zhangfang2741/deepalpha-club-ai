"""夜间调度触发时间。"""

from datetime import UTC, datetime

from app.services.quant_research.scheduler import next_trigger, us_session_date

WEEKDAYS = {0, 1, 2, 3, 4}


def test_next_trigger_same_day_and_next_day():
    after = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)  # 周三
    assert next_trigger(after, 22, 30, WEEKDAYS) == datetime(2026, 9, 30, 22, 30, tzinfo=UTC)
    after = datetime(2026, 9, 30, 23, 0, tzinfo=UTC)
    assert next_trigger(after, 22, 30, WEEKDAYS) == datetime(2026, 10, 1, 22, 30, tzinfo=UTC)


def test_next_trigger_skips_weekend():
    after = datetime(2026, 10, 2, 23, 0, tzinfo=UTC)  # 周五晚
    assert next_trigger(after, 22, 30, WEEKDAYS) == datetime(2026, 10, 5, 22, 30, tzinfo=UTC)


def test_us_session_date():
    assert us_session_date(datetime(2026, 9, 30, 22, 30, tzinfo=UTC)).isoformat() == "2026-09-30"
