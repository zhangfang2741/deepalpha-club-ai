"""Fear & Greed Index 数据获取与缓存服务."""
from datetime import date, datetime, timedelta, timezone

import httpx
from redis.asyncio import Redis

from app.cache.fear_greed_cache import get_fear_greed_cache, set_fear_greed_cache
from app.core.config import settings
from app.core.logging import logger
from app.schemas.fear_greed import FearGreedPoint, FearGreedResponse, FearGreedSnapshot

_CNN_BASE = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; deepalpha-bot/1.0)",
    "Referer": "https://edition.cnn.com/markets/fear-and-greed",
}

_RATING_MAP = {
    "extreme fear": "Extreme Fear",
    "fear": "Fear",
    "neutral": "Neutral",
    "greed": "Greed",
    "extreme greed": "Extreme Greed",
}


def _normalize_rating(raw: str) -> str:
    return _RATING_MAP.get(raw.lower(), raw.title())


def _extract_snapshot(value: dict | float | int) -> tuple[float, str | None]:
    """兼容 CNN API 两种格式：嵌套 dict 或直接 float."""
    if isinstance(value, dict):
        score = float(value["score"])
        rating = value.get("rating")
    else:
        score = float(value)
        rating = None
    return score, rating


def _score_to_rating(score: float) -> str:
    if score < 25:
        return "Extreme Fear"
    if score < 45:
        return "Fear"
    if score < 56:
        return "Neutral"
    if score < 76:
        return "Greed"
    return "Extreme Greed"


class FearGreedService:
    """CNN Fear & Greed Index 数据获取与缓存服务."""

    async def get_history(
        self,
        redis: Redis,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> FearGreedResponse:
        """检查 Redis 缓存，命中时返回缓存，未命中时调用 CNN API 并写入缓存.

        Args:
            redis: Redis client for caching.
            start_date: Filter history from this date. Defaults to 1 year ago.
            end_date: Filter history to this date. Defaults to today.
        """
        cached = await get_fear_greed_cache(redis)
        if cached is not None:
            logger.info("fear_greed_cache_hit")
            # Apply date filtering on cached data
            return self._filter_by_date_range(cached, start_date, end_date)

        logger.info("fear_greed_cache_miss")
        return await self._fetch_and_cache(redis, start_date, end_date)

    def _filter_by_date_range(
        self,
        data: FearGreedResponse,
        start_date: date | None,
        end_date: date | None,
    ) -> FearGreedResponse:
        """Filter history by date range while keeping snapshots from full dataset."""
        if not start_date and not end_date:
            return data

        filtered_history = [
            point for point in data.history
            if (not start_date or point.date >= start_date.isoformat())
            and (not end_date or point.date <= end_date.isoformat())
        ]
        return data.model_copy(update={"history": filtered_history})

    async def _fetch_and_cache(
        self,
        redis: Redis,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> FearGreedResponse:
        # Fetch 5 years of data to support various time range selections
        fetch_start = (date.today() - timedelta(days=1825)).isoformat()
        url = f"{_CNN_BASE}/{fetch_start}"
        try:
            async with httpx.AsyncClient(
                timeout=15,
                proxy=settings.HTTP_PROXY or settings.HTTPS_PROXY or None,
            ) as client:
                resp = await client.get(url, headers=_HEADERS)
                resp.raise_for_status()
                raw = resp.json()
        except Exception:
            logger.exception("fear_greed_fetch_failed", url=url)
            raise

        try:
            data = self._parse(raw)
        except (KeyError, ValueError, TypeError):
            logger.exception("fear_greed_parse_failed", url=url)
            raise

        # 数据为空时不写缓存，避免缓存空数据
        if not data.history:
            logger.warning("fear_greed_empty_data", url=url)
            return data

        await set_fear_greed_cache(redis, data)
        return data

    def _parse(self, raw: dict) -> FearGreedResponse:
        fg = raw["fear_and_greed"]
        historical = raw["fear_and_greed_historical"]["data"]

        seen: dict[str, FearGreedPoint] = {}
        for item in historical:
            ts_ms = item["x"]
            score = float(item["y"])
            dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date()
            date_str = dt.isoformat()
            rating_raw = item.get("rating", _score_to_rating(score))
            seen[date_str] = FearGreedPoint(
                date=date_str,
                score=round(score, 1),
                rating=_normalize_rating(rating_raw),
            )

        history_points = sorted(seen.values(), key=lambda p: p.date)

        scores = [p.score for p in history_points]
        low_idx = scores.index(min(scores)) if scores else 0
        high_idx = scores.index(max(scores)) if scores else 0

        current_score = round(float(fg["score"]), 1)
        current_date = datetime.fromisoformat(fg["timestamp"].split("T")[0]).date().isoformat()

        w_score, w_rating = _extract_snapshot(fg["previous_1_week"])
        m_score, m_rating = _extract_snapshot(fg["previous_1_month"])
        y_score, y_rating = _extract_snapshot(fg["previous_1_year"])

        return FearGreedResponse(
            current=FearGreedSnapshot(
                score=current_score,
                rating=_normalize_rating(fg.get("rating", _score_to_rating(current_score))),
                date=current_date,
            ),
            previous_week=FearGreedSnapshot(
                score=round(w_score, 1),
                rating=_normalize_rating(w_rating or _score_to_rating(w_score)),
            ),
            previous_month=FearGreedSnapshot(
                score=round(m_score, 1),
                rating=_normalize_rating(m_rating or _score_to_rating(m_score)),
            ),
            previous_year=FearGreedSnapshot(
                score=round(y_score, 1),
                rating=_normalize_rating(y_rating or _score_to_rating(y_score)),
            ),
            history_low=FearGreedSnapshot(
                score=history_points[low_idx].score if history_points else 0.0,
                rating=history_points[low_idx].rating if history_points else "Extreme Fear",
                date=history_points[low_idx].date if history_points else None,
            ),
            history_high=FearGreedSnapshot(
                score=history_points[high_idx].score if history_points else 100.0,
                rating=history_points[high_idx].rating if history_points else "Extreme Greed",
                date=history_points[high_idx].date if history_points else None,
            ),
            history=history_points,
        )


fear_greed_service = FearGreedService()
