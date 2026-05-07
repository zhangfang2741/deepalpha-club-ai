"""Fear & Greed Index 数据获取与缓存服务."""
from datetime import date, datetime, timedelta, timezone

import httpx
from redis.asyncio import Redis

from app.cache.fear_greed_cache import get_fear_greed_cache, set_fear_greed_cache
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

    async def get_history(self, redis: Redis) -> FearGreedResponse:
        """检查 Redis 缓存，命中时返回缓存，未命中时调用 CNN API 并写入缓存."""
        cached = await get_fear_greed_cache(redis)
        if cached is not None:
            logger.info("fear_greed_cache_hit")
            return cached

        logger.info("fear_greed_cache_miss")
        return await self._fetch_and_cache(redis)

    async def _fetch_and_cache(self, redis: Redis) -> FearGreedResponse:
        start_date = (date.today() - timedelta(days=365)).isoformat()
        url = f"{_CNN_BASE}/{start_date}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
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

        await set_fear_greed_cache(redis, data)
        return data

    def _parse(self, raw: dict) -> FearGreedResponse:
        fg = raw["fear_and_greed"]
        historical = raw["fear_and_greed_historical"]["data"]

        history_points = []
        for item in historical:
            ts_ms = item["x"]
            score = float(item["y"])
            dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date()
            rating_raw = item.get("rating", _score_to_rating(score))
            history_points.append(FearGreedPoint(
                date=dt.isoformat(),
                score=round(score, 1),
                rating=_normalize_rating(rating_raw),
            ))

        history_points.sort(key=lambda p: p.date)

        scores = [p.score for p in history_points]
        low_idx = scores.index(min(scores)) if scores else 0
        high_idx = scores.index(max(scores)) if scores else 0

        current_score = round(float(fg["score"]), 1)
        current_date = datetime.fromisoformat(fg["timestamp"].split("T")[0]).date().isoformat()

        return FearGreedResponse(
            current=FearGreedSnapshot(
                score=current_score,
                rating=_normalize_rating(fg.get("rating", _score_to_rating(current_score))),
                date=current_date,
            ),
            previous_week=FearGreedSnapshot(
                score=round(float(fg["previous_1_week"]["score"]), 1),
                rating=_normalize_rating(
                    fg["previous_1_week"].get("rating", _score_to_rating(fg["previous_1_week"]["score"]))
                ),
            ),
            previous_month=FearGreedSnapshot(
                score=round(float(fg["previous_1_month"]["score"]), 1),
                rating=_normalize_rating(
                    fg["previous_1_month"].get("rating", _score_to_rating(fg["previous_1_month"]["score"]))
                ),
            ),
            previous_year=FearGreedSnapshot(
                score=round(float(fg["previous_1_year"]["score"]), 1),
                rating=_normalize_rating(
                    fg["previous_1_year"].get("rating", _score_to_rating(fg["previous_1_year"]["score"]))
                ),
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
