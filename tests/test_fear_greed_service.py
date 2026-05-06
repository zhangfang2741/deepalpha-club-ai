"""Fear & Greed Service 单元测试（mock CNN API 响应）。"""
import time
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.fear_greed import FearGreedService, _normalize_rating, _score_to_rating


def test_normalize_rating_maps_all_variants():
    assert _normalize_rating("extreme fear") == "Extreme Fear"
    assert _normalize_rating("fear") == "Fear"
    assert _normalize_rating("neutral") == "Neutral"
    assert _normalize_rating("greed") == "Greed"
    assert _normalize_rating("extreme greed") == "Extreme Greed"
    assert _normalize_rating("Extreme Greed") == "Extreme Greed"


def test_score_to_rating_boundaries():
    assert _score_to_rating(0) == "Extreme Fear"
    assert _score_to_rating(24.9) == "Extreme Fear"
    assert _score_to_rating(25) == "Fear"
    assert _score_to_rating(44.9) == "Fear"
    assert _score_to_rating(45) == "Neutral"
    assert _score_to_rating(55.9) == "Neutral"
    assert _score_to_rating(56) == "Greed"
    assert _score_to_rating(75.9) == "Greed"
    assert _score_to_rating(76) == "Extreme Greed"
    assert _score_to_rating(100) == "Extreme Greed"


@pytest.mark.asyncio
async def test_get_history_returns_cached_data():
    """缓存命中时直接返回，不调用 CNN API。"""
    from app.schemas.fear_greed import FearGreedPoint, FearGreedResponse, FearGreedSnapshot

    mock_redis = AsyncMock()
    cached = FearGreedResponse(
        current=FearGreedSnapshot(score=72, rating="Greed", date="2026-05-06"),
        previous_week=FearGreedSnapshot(score=38, rating="Fear"),
        previous_month=FearGreedSnapshot(score=51, rating="Neutral"),
        previous_year=FearGreedSnapshot(score=52, rating="Neutral"),
        history_low=FearGreedSnapshot(score=2, rating="Extreme Fear", date="2022-10-12"),
        history_high=FearGreedSnapshot(score=97, rating="Extreme Greed", date="2021-11-09"),
        history=[FearGreedPoint(date="2025-05-06", score=38, rating="Fear")],
    )

    with patch("app.services.fear_greed.get_fear_greed_cache", new_callable=AsyncMock) as mock_cache:
        mock_cache.return_value = cached
        service = FearGreedService()
        result = await service.get_history(mock_redis)

    assert result.current.score == 72
    mock_cache.assert_called_once_with(mock_redis)


@pytest.mark.asyncio
async def test_get_history_fetches_from_cnn_on_cache_miss():
    """缓存未命中时调用 CNN API 并写入缓存。"""
    today = date.today()
    start_date = today - timedelta(days=365)
    ts_ms = int(time.mktime(start_date.timetuple())) * 1000

    cnn_payload = {
        "fear_and_greed": {
            "score": 72.1,
            "rating": "Greed",
            "timestamp": f"{today.isoformat()}T00:00:00",
            "previous_1_week": {"score": 38.0, "rating": "Fear"},
            "previous_1_month": {"score": 51.0, "rating": "Neutral"},
            "previous_1_year": {"score": 52.0, "rating": "Neutral"},
        },
        "fear_and_greed_historical": {
            "data": [{"x": ts_ms, "y": 38.0}]
        },
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = cnn_payload
    mock_response.raise_for_status = MagicMock()

    mock_redis = AsyncMock()

    with (
        patch("app.services.fear_greed.get_fear_greed_cache", new_callable=AsyncMock, return_value=None),
        patch("app.services.fear_greed.set_fear_greed_cache", new_callable=AsyncMock) as mock_set,
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        service = FearGreedService()
        result = await service.get_history(mock_redis)

    assert result.current.score == pytest.approx(72.1, abs=0.1)
    assert result.current.rating == "Greed"
    assert len(result.history) == 1
    mock_set.assert_called_once()
