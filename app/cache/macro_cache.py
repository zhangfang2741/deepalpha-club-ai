"""宏观环境 / 市场概览的 Redis 缓存。

key：
- macro:resp:{market}:{lang}        宏观弹层，TTL 10 分钟
- macro:overview:{market}:{lang}    顶部两格摘要，TTL 10 分钟
- macro:sectors:{market}:{parent}:{lang}  行业弹层，TTL 10 分钟
- macro:series:{market}:{date}      驱动因素原始序列，TTL 1 小时
- macro:calendar:{date}             宏观日历原始事件，TTL 6 小时
regime 每日重算后调用 drop_market 清掉该市场的响应缓存。
"""
from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel
from redis.asyncio import Redis

from app.core.logging import logger

RESPONSE_TTL = 600
SERIES_TTL = 3600
CALENDAR_TTL = 6 * 3600

M = TypeVar("M", bound=BaseModel)


async def get_model(redis: Redis | None, key: str, model: type[M]) -> M | None:
    """读缓存并反序列化成模型；未命中或出错返回 None。"""
    if redis is None:
        return None
    try:
        raw = await redis.get(key)
        return model.model_validate_json(raw) if raw else None
    except Exception as e:  # noqa: BLE001
        logger.warning("macro_cache_read_failed", key=key, error=str(e))
        return None


async def set_model(redis: Redis | None, key: str, value: BaseModel, ttl: int = RESPONSE_TTL) -> None:
    """模型写缓存；出错只记日志。"""
    if redis is None:
        return
    try:
        await redis.set(key, value.model_dump_json(), ex=ttl)
    except Exception as e:  # noqa: BLE001
        logger.warning("macro_cache_write_failed", key=key, error=str(e))


async def get_json(redis: Redis | None, key: str) -> object | None:
    """读 JSON 缓存；未命中或出错返回 None。"""
    if redis is None:
        return None
    try:
        raw = await redis.get(key)
        return json.loads(raw) if raw else None
    except Exception as e:  # noqa: BLE001
        logger.warning("macro_cache_read_failed", key=key, error=str(e))
        return None


async def set_json(redis: Redis | None, key: str, value: object, ttl: int) -> None:
    """写 JSON 缓存；出错只记日志。"""
    if redis is None:
        return
    try:
        await redis.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
    except Exception as e:  # noqa: BLE001
        logger.warning("macro_cache_write_failed", key=key, error=str(e))


async def drop_market(redis: Redis | None, market: str) -> None:
    """regime 重算后清掉该市场的弹层 / 摘要 / 行业缓存（原始序列与日历不受影响）。"""
    if redis is None:
        return
    try:
        keys = []
        for pattern in (f"macro:resp:{market}:*", f"macro:overview:{market}:*", f"macro:sectors:{market}:*"):
            keys += [k async for k in redis.scan_iter(match=pattern, count=100)]
        if keys:
            await redis.unlink(*keys)
    except Exception as e:  # noqa: BLE001
        logger.warning("macro_cache_drop_failed", market=market, error=str(e))
