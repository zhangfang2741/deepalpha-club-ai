"""Fear & Greed Index schema 验证测试。"""
import pytest
from pydantic import ValidationError
from app.schemas.fear_greed import (
    FearGreedPoint,
    FearGreedSnapshot,
    FearGreedResponse,
)


def test_fear_greed_point_valid():
    point = FearGreedPoint(date="2025-05-06", score=38, rating="Fear")
    assert point.score == 38
    assert point.rating == "Fear"
    assert point.date == "2025-05-06"


def test_fear_greed_point_rejects_out_of_range_score():
    with pytest.raises(ValidationError):
        FearGreedPoint(date="2025-05-06", score=101, rating="Extreme Greed")


def test_fear_greed_point_rejects_negative_score():
    with pytest.raises(ValidationError):
        FearGreedPoint(date="2025-05-06", score=-1, rating="Extreme Fear")


def test_fear_greed_snapshot_no_date():
    snap = FearGreedSnapshot(score=72, rating="Greed")
    assert snap.score == 72
    assert snap.date is None


def test_fear_greed_snapshot_with_date():
    snap = FearGreedSnapshot(score=2, rating="Extreme Fear", date="2022-10-12")
    assert snap.date == "2022-10-12"


def test_fear_greed_response_structure():
    resp = FearGreedResponse(
        current=FearGreedSnapshot(score=72, rating="Greed", date="2026-05-06"),
        previous_week=FearGreedSnapshot(score=38, rating="Fear"),
        previous_month=FearGreedSnapshot(score=51, rating="Neutral"),
        previous_year=FearGreedSnapshot(score=52, rating="Neutral"),
        history_low=FearGreedSnapshot(score=2, rating="Extreme Fear", date="2022-10-12"),
        history_high=FearGreedSnapshot(score=97, rating="Extreme Greed", date="2021-11-09"),
        history=[FearGreedPoint(date="2025-05-06", score=38, rating="Fear")],
    )
    assert len(resp.history) == 1
    assert resp.current.score == 72
