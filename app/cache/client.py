# app/cache/client.py
"""Redis 连接管理：连接池 + FastAPI 依赖注入 + 健康检查。

与 app/core/cache.py 的关系：
  - app/core/cache.py 的 ValkeyCacheService 供 lifespan 内部使用（API 响应缓存）
  - 本模块提供面向业务端点的 get_redis() 依赖注入，支持直接操作 Redis
"""

from collections.abc import AsyncGenerator
from typing import Optional

from redis.asyncio import ConnectionPool, Redis

from app.core.config import settings
from app.core.logging import logger

# 全局连接池（在 lifespan 中通过 init_redis() 初始化）
_pool: Optional[ConnectionPool] = None
_client: Optional[Redis] = None


async def init_redis() -> None:
    """初始化 Redis 连接池，在应用启动时调用。"""
    global _pool, _client

    host = settings.VALKEY_HOST or "localhost"
    _pool = ConnectionPool(
        host=host,
        port=settings.VALKEY_PORT,
        db=settings.VALKEY_DB,
        password=settings.VALKEY_PASSWORD or None,
        max_connections=settings.VALKEY_MAX_CONNECTIONS,
        decode_responses=True,
    )
    _client = Redis(connection_pool=_pool)
    await _client.ping()
    logger.info(
        "redis_client_initialized",
        host=host,
        port=settings.VALKEY_PORT,
        max_connections=settings.VALKEY_MAX_CONNECTIONS,
    )


async def close_redis() -> None:
    """关闭 Redis 连接，在应用关闭时调用。"""
    global _client, _pool
    if _client:
        await _client.aclose()
        _client = None
    if _pool:
        await _pool.aclose()
        _pool = None
    logger.info("redis_client_closed")


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI 依赖注入函数。

    用法：
        async def my_endpoint(redis: Redis = Depends(get_redis)):
            value = await redis.get("key")
    """
    if _client is None:
        raise RuntimeError("Redis 未初始化，请检查应用启动流程")
    yield _client


async def health_check() -> bool:
    """检查 Redis 连接健康状态。"""
    try:
        if _client:
            await _client.ping()
            return True
        return False
    except Exception as e:
        logger.warning("redis_health_check_failed", error=str(e))
        return False
