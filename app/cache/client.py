# app/cache/client.py
"""Redis 连接管理：连接池 + FastAPI 依赖注入 + 健康检查。

与 app/core/cache.py 的关系：
  - app/core/cache.py 的 ValkeyCacheService 供 lifespan 内部使用（API 响应缓存）
  - 本模块提供面向业务端点的 get_redis() 依赖注入，支持直接操作 Redis
"""

from collections.abc import AsyncGenerator
from typing import Optional

from redis.asyncio import ConnectionPool, Redis, SSLConnection

from app.core.config import settings
from app.core.logging import logger

# 全局连接池（在 lifespan 中通过 init_redis() 初始化）
_pool: Optional[ConnectionPool] = None
_client: Optional[Redis] = None


async def init_redis() -> None:
    """初始化 Redis 连接池，在应用启动时调用。"""
    global _pool, _client

    host = settings.VALKEY_HOST or "localhost"
    pool_kwargs: dict = {
        "host": host,
        "port": settings.VALKEY_PORT,
        "db": settings.VALKEY_DB,
        "password": settings.VALKEY_PASSWORD or None,
        "max_connections": settings.VALKEY_MAX_CONNECTIONS,
        "decode_responses": False,
    }
    if settings.VALKEY_SSL:
        pool_kwargs["connection_class"] = SSLConnection
    _pool = ConnectionPool(**pool_kwargs)
    _client = Redis(connection_pool=_pool)
    try:
        await _client.ping()  # type: ignore[misc]
    except Exception:
        # ping 失败说明 Redis 不可用；重置为 None 让 get_redis_optional 能正确降级
        _client = None
        raise
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


async def get_redis_optional() -> AsyncGenerator[Optional[Redis], None]:
    """可选 Redis 依赖：Redis 不可用时 yield None，端点自行降级处理。"""
    yield _client


def current_redis() -> Optional[Redis]:
    """返回当前 Redis 客户端（未初始化时为 None）。

    供非 FastAPI 依赖注入场景使用（如 LangGraph 工具），让其也能复用缓存。
    """
    return _client


async def health_check() -> bool:
    """检查 Redis 连接健康状态。"""
    try:
        if _client:
            await _client.ping()  # type: ignore[misc]
            return True
        return False
    except Exception as e:
        logger.warning("redis_health_check_failed", error=str(e))
        return False
