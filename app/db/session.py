# app/db/session.py
"""双引擎 Session 管理：AsyncSession（FastAPI 异步端点）+ SyncSession（Celery 任务）。"""

from collections.abc import AsyncGenerator, Generator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import QueuePool
from sqlmodel import Session, create_engine

from app.core.config import settings

# 构建连接字符串基础部分
_PG_BASE = (
    f"{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
)

# SSL 参数（Supabase/云数据库需要）
_PG_SSL_QUERY = "?sslmode=require" if settings.POSTGRES_SSL else ""

# 同步引擎（Celery 任务 / 兼容现有 DatabaseService）
sync_engine = create_engine(
    f"postgresql://{_PG_BASE}{_PG_SSL_QUERY}",
    pool_pre_ping=True,
    poolclass=QueuePool,
    pool_size=settings.POSTGRES_POOL_SIZE,
    max_overflow=settings.POSTGRES_MAX_OVERFLOW,
    pool_timeout=30,
    pool_recycle=1800,
)

# 异步引擎（FastAPI 异步端点用）
async_engine = create_async_engine(
    f"postgresql+asyncpg://{_PG_BASE}{_PG_SSL_QUERY}",
    pool_pre_ping=True,
    pool_size=settings.POSTGRES_POOL_SIZE,
    max_overflow=settings.POSTGRES_MAX_OVERFLOW,
    pool_timeout=30,
    pool_recycle=1800,
)

# 异步 session 工厂
AsyncSessionFactory = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def get_sync_session() -> Generator[Session, None, None]:
    """Celery 任务用同步 session 依赖。"""
    with Session(sync_engine) as session:
        yield session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 异步端点依赖注入函数。

    用法：
        async def my_endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionFactory() as session:
        yield session
