"""真太阳时校正测试。"""

from datetime import datetime

from app.services.bazi.true_solar_time import correct_birth_datetime


def test_correct_birth_datetime_known_city_applies_offset():
    """北京经度116.4074，比东八区中心线120°偏西，应校正为更早的时间。"""
    dt = datetime(1990, 5, 15, 14, 30, 0)
    corrected, applied = correct_birth_datetime(dt, "北京")
    assert applied is True
    assert corrected == datetime(1990, 5, 15, 14, 16, 0)


def test_correct_birth_datetime_unknown_city_returns_original():
    """命中不到城市表时，原样返回输入时间，且标记为未校正。"""
    dt = datetime(1990, 5, 15, 14, 30, 0)
    corrected, applied = correct_birth_datetime(dt, "东京")
    assert applied is False
    assert corrected == dt


def test_correct_birth_datetime_strips_whitespace_in_city_name():
    """城市名带首尾空格时，去除空格后仍应命中经度表并完成校正。"""
    dt = datetime(1990, 5, 15, 14, 30, 0)
    corrected, applied = correct_birth_datetime(dt, " 北京 ")
    assert applied is True
    assert corrected == datetime(1990, 5, 15, 14, 16, 0)
