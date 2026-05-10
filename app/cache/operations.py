# app/cache/operations.py
"""Redis 业务操作封装：基础 CRUD、JSON、Session（JWT）、限流、缓存。

所有函数接收 redis: Redis 参数，通过 Depends(get_redis) 注入使用。

示例：
    async def my_endpoint(redis: Redis = Depends(get_redis)):
        await set_session(redis, user_id="123", token="jwt_token")
"""

import json
import time
from typing import Any, Optional

from redis.asyncio import Redis

from app.core.logging import logger


# ---------- 基础操作 ----------

async def get(redis: Redis, key: str) -> Optional[str]:
    """获取字符串值，key 不存在返回 None。"""
    raw = await redis.get(key)
    if raw is None:
        return None
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return str(raw)


async def set(redis: Redis, key: str, value: Any, expire: Optional[int] = None) -> None:
    """设置字符串值，expire 为秒数（None 表示永不过期）。"""
    await redis.set(key, str(value), ex=expire)


async def delete(redis: Redis, key: str) -> None:
    """删除指定 key。"""
    await redis.delete(key)


async def exists(redis: Redis, key: str) -> bool:
    """检查 key 是否存在，返回 True/False。"""
    return bool(await redis.exists(key))


# ---------- JSON 操作 ----------

async def get_json(redis: Redis, key: str) -> Optional[dict]:
    """获取 JSON 对象，key 不存在或解析失败返回 None。"""
    raw = await redis.get(key)
    if raw is None:
        return None
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("cache_json_decode_error", key=key, error=str(e))
        return None


async def set_json(redis: Redis, key: str, value: dict, expire: Optional[int] = None) -> None:
    """存储 JSON 对象，expire 为秒数（None 表示永不过期）。"""
    await redis.set(key, json.dumps(value, ensure_ascii=False), ex=expire)


# ---------- Session 操作（用于 JWT Token 管理）----------

_SESSION_PREFIX = "session"


async def set_session(redis: Redis, user_id: str, token: str, expire: int = 86400) -> None:
    """存储用户 JWT Session，默认 24 小时过期。

    key 格式：session:{user_id}
    """
    key = f"{_SESSION_PREFIX}:{user_id}"
    await redis.set(key, token, ex=expire)
    logger.info("session_stored", user_id=user_id, expire=expire)


async def get_session(redis: Redis, user_id: str) -> Optional[str]:
    """获取用户 JWT Session Token，不存在或已过期返回 None。"""
    key = f"{_SESSION_PREFIX}:{user_id}"
    raw = await redis.get(key)
    if raw is None:
        return None
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return str(raw)


async def delete_session(redis: Redis, user_id: str) -> None:
    """删除用户 Session（登出时调用）。"""
    key = f"{_SESSION_PREFIX}:{user_id}"
    await redis.delete(key)
    logger.info("session_deleted", user_id=user_id)


# ---------- 限流操作 ----------

async def check_rate_limit(redis: Redis, key: str, limit: int, window: int) -> bool:
    """滑动窗口限流检查。

    Args:
        redis: Redis 客户端
        key: 限流标识（如 f"rate:{user_id}:{endpoint}"）
        limit: 窗口内最大请求数
        window: 时间窗口（秒）

    Returns:
        True 表示允许请求，False 表示超出限制
    """
    now = time.time()
    window_start = now - window
    pipe = redis.pipeline()
    # 移除时间窗口之外的旧记录
    pipe.zremrangebyscore(key, 0, window_start)
    # 记录当前请求时间戳（用时间戳作为 member 和 score）
    pipe.zadd(key, {str(now): now})
    # 设置 key 过期，防止内存泄漏
    pipe.expire(key, window)
    # 统计当前窗口内的请求数量
    pipe.zcard(key)
    results = await pipe.execute()
    current_count = results[-1]
    return int(current_count) <= limit


# ---------- 缓存操作 ----------

async def cache_result(redis: Redis, key: str, value: Any, expire: int = 3600) -> None:
    """缓存任意可 JSON 序列化的结果，默认 1 小时过期。"""
    await set_json(redis, key, {"data": value}, expire=expire)


async def invalidate_cache(redis: Redis, pattern: str) -> int:
    """按 glob 模式批量删除缓存 key，返回删除数量。

    示例：
        await invalidate_cache(redis, "user:123:*")   # 删除用户所有缓存
        await invalidate_cache(redis, "chat:*")       # 删除所有聊天缓存
    """
    keys = await redis.keys(pattern)
    if not keys:
        return 0
    count = await redis.delete(*keys)
    logger.info("cache_invalidated", pattern=pattern, count=count)
    return count
