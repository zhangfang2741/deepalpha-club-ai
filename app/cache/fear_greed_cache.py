"""Fear & Greed Index Redis 缓存操作。

key: fear_greed:history:1y
TTL: 3600 秒
"""
import json
from typing import Optional

from redis.asyncio import Redis

from app.core.logging import logger
from app.schemas.fear_greed import FearGreedResponse

FEAR_GREED_CACHE_KEY = "fear_greed:history:1y"
FEAR_GREED_TTL = 3600


async def get_fear_greed_cache(redis: Redis) -> Optional[FearGreedResponse]:
    """读取缓存，未命中或反序列化失败返回 None。"""
    raw = await redis.get(FEAR_GREED_CACHE_KEY)
    if raw is None:
        return None
    try:
        return FearGreedResponse.model_validate(json.loads(raw))
    except Exception as e:
        logger.warning("fear_greed_cache_deserialize_error", error=str(e))
        return None


async def set_fear_greed_cache(redis: Redis, data: FearGreedResponse) -> None:
    """将数据写入 Redis，TTL = 3600s。出错时记录日志，不抛出异常（保留现有缓存）。"""
    try:
        payload = json.dumps(data.model_dump(mode="json"), ensure_ascii=False)
        await redis.set(FEAR_GREED_CACHE_KEY, payload, ex=FEAR_GREED_TTL)
        logger.info("fear_greed_cache_set", ttl=FEAR_GREED_TTL)
    except Exception as e:
        logger.warning("fear_greed_cache_set_error", error=str(e))
