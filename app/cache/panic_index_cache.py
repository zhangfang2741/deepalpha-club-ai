"""三地恐慌指数 Redis 缓存操作。

key: panic_index:history:{market}
TTL: 3600 秒（原始数据是日频，缓存周期不需要比 fear_greed 更短）
"""
import json
from typing import Optional

from redis.asyncio import Redis

from app.core.logging import logger
from app.schemas.panic_index import PanicIndexResponse

PANIC_INDEX_TTL = 3600


def _cache_key(market: str) -> str:
    return f"panic_index:history:{market}"


async def get_panic_index_cache(redis: Redis, market: str) -> Optional[PanicIndexResponse]:
    """读取缓存，未命中或反序列化失败返回 None。"""
    raw = await redis.get(_cache_key(market))
    if raw is None:
        return None
    try:
        return PanicIndexResponse.model_validate(json.loads(raw))
    except Exception as e:
        logger.warning("panic_index_cache_deserialize_error", market=market, error=str(e))
        return None


async def set_panic_index_cache(redis: Redis, market: str, data: PanicIndexResponse) -> None:
    """将数据写入 Redis，TTL = 3600s。出错时记录日志，不抛出异常（保留现有缓存）。"""
    try:
        payload = json.dumps(data.model_dump(mode="json"), ensure_ascii=False)
        await redis.set(_cache_key(market), payload, ex=PANIC_INDEX_TTL)
        logger.info("panic_index_cache_set", market=market, ttl=PANIC_INDEX_TTL)
    except Exception as e:
        logger.warning("panic_index_cache_set_error", market=market, error=str(e))
