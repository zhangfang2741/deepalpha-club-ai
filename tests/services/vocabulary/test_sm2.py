"""SM-2 间隔重复算法单元测试。"""
import datetime

import pytest

from app.services.vocabulary.sm2 import MIN_EASINESS_FACTOR, apply_review

FIXED_NOW = datetime.datetime(2026, 7, 25, 12, 0, 0, tzinfo=datetime.UTC)


def test_unknown_rating_resets_repetition_and_short_interval():
    result = apply_review(rating=0, repetition_count=5, easiness_factor=2.6, interval_days=30, now=FIXED_NOW)
    assert result.repetition_count == 0
    assert result.interval_days == 1
    assert result.status == "new"
    assert result.next_review_at == FIXED_NOW + datetime.timedelta(days=1)


def test_fuzzy_rating_keeps_repetition_short_interval_lowers_ef():
    result = apply_review(rating=1, repetition_count=2, easiness_factor=2.5, interval_days=6, now=FIXED_NOW)
    assert result.repetition_count == 2
    assert result.interval_days == 1
    assert result.easiness_factor == pytest.approx(2.35)
    assert result.status == "fuzzy"


def test_known_rating_first_repetition_sets_interval_to_one_day():
    result = apply_review(rating=2, repetition_count=0, easiness_factor=2.5, interval_days=0, now=FIXED_NOW)
    assert result.repetition_count == 1
    assert result.interval_days == 1
    assert result.easiness_factor == pytest.approx(2.6)
    assert result.status == "known"


def test_known_rating_second_repetition_sets_interval_to_six_days():
    result = apply_review(rating=2, repetition_count=1, easiness_factor=2.6, interval_days=1, now=FIXED_NOW)
    assert result.repetition_count == 2
    assert result.interval_days == 6
    assert result.status == "known"


def test_known_rating_third_repetition_multiplies_interval_by_ef():
    result = apply_review(rating=2, repetition_count=2, easiness_factor=2.6, interval_days=6, now=FIXED_NOW)
    assert result.repetition_count == 3
    assert result.easiness_factor == pytest.approx(2.7)
    assert result.interval_days == 16  # round(6 * 2.7) = 16
    assert result.status == "known"


def test_known_rating_fourth_repetition_multiplies_interval_by_ef():
    result = apply_review(rating=2, repetition_count=3, easiness_factor=2.7, interval_days=16, now=FIXED_NOW)
    assert result.repetition_count == 4
    assert result.interval_days == 45  # round(16 * 2.8) = 45
    assert result.status == "known"


def test_easiness_factor_never_drops_below_minimum():
    result = apply_review(
        rating=1, repetition_count=0, easiness_factor=MIN_EASINESS_FACTOR, interval_days=1, now=FIXED_NOW
    )
    assert result.easiness_factor == MIN_EASINESS_FACTOR


def test_invalid_rating_raises_value_error():
    with pytest.raises(ValueError):
        apply_review(rating=3, repetition_count=0, easiness_factor=2.5, interval_days=0, now=FIXED_NOW)
