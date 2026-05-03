# 项目初始化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于 wassim249/fastapi-langgraph-agent-production-ready-template 初始化一个支持多 LLM 供应商、异步数据库、Redis 缓存、Next.js 前端的生产就绪 AI Agent 项目。

**Architecture:** 后端沿用模板的 FastAPI + LangGraph + SQLModel 架构，在 `app/db/` 新增 AsyncSession 支持，在 `app/cache/` 新增业务操作封装。前端用 Next.js 14 + shadcn/ui + Zustand 实现独立的认证和聊天界面。LLM 层扩展 Claude / MiniMax / Gemini 多供应商支持。

**Tech Stack:** Python 3.13 + uv / FastAPI / LangGraph / SQLModel + asyncpg / Redis(redis-py asyncio) / Next.js 14 / TypeScript / Tailwind + shadcn / Zustand / Docker Compose

---

## 分析结果摘要

### 现有目录结构（模板）

```
.
├── app/
│   ├── api/v1/          # auth.py, chatbot.py, api.py
│   ├── core/
│   │   ├── cache.py     # ValkeyCacheService + InMemoryCacheService (已完整)
│   │   ├── config.py    # Settings 类 (已有 Postgres/Valkey/JWT)
│   │   ├── langgraph/   # LangGraph graph + tools
│   │   ├── limiter.py   # 限流
│   │   ├── logging.py   # 结构化日志
│   │   ├── metrics.py   # Prometheus
│   │   └── middleware.py
│   ├── models/
│   │   ├── base.py      # BaseModel (只有 created_at，无 id/updated_at)
│   │   ├── session.py   # ChatSession (str id)
│   │   ├── thread.py    # Thread
│   │   └── user.py      # User (int id, bcrypt)
│   ├── schemas/         # Pydantic schemas
│   ├── services/
│   │   ├── database.py  # DatabaseService (同步 SQLModel Session)
│   │   ├── llm/         # LLM registry (仅 OpenAI)
│   │   └── memory.py    # mem0 长期记忆
│   └── main.py          # lifespan (cache init/close)
├── alembic/             # 迁移已配置
├── docker-compose.yml   # Postgres 16(pgvector) + Valkey + app + Prometheus + Grafana
├── pyproject.toml       # uv 管理
└── .env.example
```

### 复用策略

| 文件                             | 策略   | 说明                       |
| ------------------------------ | ---- | ------------------------ |
| `app/core/cache.py`            | 直接复用 | ValkeyCacheService 完整可用  |
| `app/services/database.py`     | 直接复用 | 同步 DatabaseService 保留    |
| `app/core/config.py`           | 修改扩展 | 添加 LLM 多供应商字段            |
| `app/models/base.py`           | 直接复用 | 保留给现有模型                  |
| `app/services/llm/registry.py` | 修改扩展 | 添加 Claude/MiniMax/Gemini |
| `docker-compose.yml`           | 直接复用 | 本地 Valkey+Postgres 已完整   |
| `app/main.py`                  | 直接复用 | lifespan 已有 cache 管理     |

### 新增文件

| 文件                           | 说明                                    |
| ---------------------------- | ------------------------------------- |
| `app/db/session.py`          | AsyncSession + SyncSession + get_db() |
| `app/db/base.py`             | UUID 主键基础模型（新 model 用）                |
| `app/cache/client.py`        | Redis 依赖注入封装                          |
| `app/cache/operations.py`    | session/rate_limit/cache 业务操作         |
| `frontend/`                  | Next.js 14 + shadcn/ui                |
| `frontend/lib/api/client.ts` | Axios 客户端                             |
| `frontend/lib/api/auth.ts`   | 认证 API                                |
| `frontend/lib/store/auth.ts` | Zustand 认证状态                          |
| `Procfile`                   | Railway 部署                            |
| `infra/docker-compose.yml`   | 含前端的本地开发 compose                      |
| `CLAUDE.md`                  | 项目专属规则（替换模板原有）                        |

---

## Task 0: 克隆项目并完成初始设置

> 前置条件：确定项目目录名称

**Files:**

- Create: `<PROJECT_DIR>/` (通过 git clone)

- [ ] **Step 1: 确认项目目录并克隆**

```bash
# 替换 my-ai-agent 为你的实际项目名
export PROJECT_DIR="/Users/zhangfang/PycharmProjects/my-ai-agent"
mkdir -p "$PROJECT_DIR"
git clone https://github.com/wassim249/fastapi-langgraph-agent-production-ready-template "$PROJECT_DIR"
cd "$PROJECT_DIR"
```

预期输出：`Cloning into ...` 成功，`ls` 可见 `app/ alembic/ pyproject.toml` 等文件

- [ ] **Step 2: 将计划文件移入项目**

```bash
mkdir -p docs/superpowers/plans
# 将本计划文件复制到项目内
```

- [ ] **Step 3: 添加 asyncpg 依赖（AsyncSession 需要）**

```bash
cd "$PROJECT_DIR"
uv add asyncpg
uv add "redis[asyncio]>=5.0.0"
```

预期输出：`uv.lock` 更新，`Resolved X packages`

- [ ] **Step 4: 添加多 LLM 供应商依赖**

```bash
uv add langchain-anthropic langchain-google-genai
```

预期输出：`Resolved X packages`

- [ ] **Step 5: 验证环境**

```bash
uv run python -c "import asyncpg; import redis.asyncio; import langchain_anthropic; print('依赖检查通过')"
```

预期输出：`依赖检查通过`

---

## Task 1: 创建 app/db/session.py（双引擎 Session 管理）

**Files:**

- Create: `app/db/__init__.py`

- Create: `app/db/session.py`

- [ ] **Step 1: 创建 `app/db/__init__.py`**

```python
# app/db/__init__.py
```

- [ ] **Step 2: 创建 `app/db/session.py`**

```python
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

# 构建连接字符串
_PG_BASE = (
    f"{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
)

# 同步引擎（Celery 任务 / 兼容现有 DatabaseService）
sync_engine = create_engine(
    f"postgresql://{_PG_BASE}",
    pool_pre_ping=True,
    poolclass=QueuePool,
    pool_size=settings.POSTGRES_POOL_SIZE,
    max_overflow=settings.POSTGRES_MAX_OVERFLOW,
    pool_timeout=30,
    pool_recycle=1800,
)

# 异步引擎（FastAPI 异步端点用）
async_engine = create_async_engine(
    f"postgresql+asyncpg://{_PG_BASE}",
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
```

- [ ] **Step 3: 验证语法**

```bash
uv run python -c "from app.db.session import get_db, get_sync_session, async_engine, sync_engine; print('session.py 语法正确')"
```

预期输出：`session.py 语法正确`

- [ ] **Step 4: 提交**

```bash
git add app/db/__init__.py app/db/session.py
git commit -m "feat: 添加 app/db/session.py 双引擎 session 管理"
```

---

## Task 2: 创建 app/db/base.py（UUID 基础模型）

**Files:**

- Create: `app/db/base.py`

> 注：现有 `app/models/base.py` 保留（User/Session 用 int id），新模型继承此 UUID base

- [ ] **Step 1: 创建 `app/db/base.py`**

```python
# app/db/base.py
"""新模型的 UUID 主键基础类。现有 User/Session 模型继续使用 app/models/base.py。"""

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class UUIDModel(SQLModel):
    """带 UUID 主键、创建时间、更新时间的公共基础模型。

    所有新 SQLModel 表模型应继承此类（而非 app/models/base.BaseModel）。
    """

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        nullable=False,
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )
```

- [ ] **Step 2: 验证语法**

```bash
uv run python -c "from app.db.base import UUIDModel; print('UUIDModel 导入成功')"
```

预期输出：`UUIDModel 导入成功`

- [ ] **Step 3: 提交**

```bash
git add app/db/base.py
git commit -m "feat: 添加 app/db/base.py UUID 基础模型"
```

---

## Task 3: 创建 app/cache/client.py（Redis 连接管理）

**Files:**

- Create: `app/cache/__init__.py`
- Create: `app/cache/client.py`

> 注：`app/core/cache.py` 的 `ValkeyCacheService` 保留（lifespan 中使用），
> 本文件新增面向 FastAPI 依赖注入的独立 Redis 客户端。

- [ ] **Step 1: 创建 `app/cache/__init__.py`**

```python
# app/cache/__init__.py
```

- [ ] **Step 2: 创建 `app/cache/client.py`**

```python
# app/cache/client.py
"""Redis 连接管理：连接池 + FastAPI 依赖注入 + 健康检查。"""

from collections.abc import AsyncGenerator
from typing import Optional

from redis.asyncio import ConnectionPool, Redis

from app.core.config import settings
from app.core.logging import logger

# 全局连接池（在 lifespan 中初始化）
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
            ...
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
```

- [ ] **Step 3: 验证语法**

```bash
uv run python -c "from app.cache.client import init_redis, close_redis, get_redis, health_check; print('client.py 语法正确')"
```

预期输出：`client.py 语法正确`

- [ ] **Step 4: 提交**

```bash
git add app/cache/__init__.py app/cache/client.py
git commit -m "feat: 添加 app/cache/client.py Redis 连接管理"
```

---

## Task 4: 创建 app/cache/operations.py（业务操作封装）

**Files:**

- Create: `app/cache/operations.py`

- [ ] **Step 1: 创建 `app/cache/operations.py`**

```python
# app/cache/operations.py
"""Redis 业务操作封装：基础 CRUD、JSON、Session（JWT）、限流、缓存。"""

import json
import time
from typing import Any, Optional

from redis.asyncio import Redis

from app.core.logging import logger


# ---------- 基础操作 ----------

async def get(redis: Redis, key: str) -> Optional[str]:
    """获取字符串值，不存在返回 None。"""
    return await redis.get(key)


async def set(redis: Redis, key: str, value: Any, expire: Optional[int] = None) -> None:
    """设置字符串值，expire 为秒数（None 表示永不过期）。"""
    await redis.set(key, str(value), ex=expire)


async def delete(redis: Redis, key: str) -> None:
    """删除指定 key。"""
    await redis.delete(key)


async def exists(redis: Redis, key: str) -> bool:
    """检查 key 是否存在。"""
    return bool(await redis.exists(key))


# ---------- JSON 操作 ----------

async def get_json(redis: Redis, key: str) -> Optional[dict]:
    """获取 JSON 对象，不存在或解析失败返回 None。"""
    raw = await redis.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("cache_json_decode_error", key=key, error=str(e))
        return None


async def set_json(redis: Redis, key: str, value: dict, expire: Optional[int] = None) -> None:
    """存储 JSON 对象，expire 为秒数。"""
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
    """获取用户 JWT Session Token，不存在返回 None。"""
    key = f"{_SESSION_PREFIX}:{user_id}"
    return await redis.get(key)


async def delete_session(redis: Redis, user_id: str) -> None:
    """删除用户 Session（登出）。"""
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
        True 表示允许，False 表示超限
    """
    now = time.time()
    window_start = now - window
    pipe = redis.pipeline()
    # 移除窗口外的旧记录
    await pipe.zremrangebyscore(key, 0, window_start)
    # 添加当前请求时间戳
    await pipe.zadd(key, {str(now): now})
    # 设置 key 过期（防止内存泄漏）
    await pipe.expire(key, window)
    # 统计窗口内请求数
    await pipe.zcard(key)
    results = await pipe.execute()
    current_count = results[-1]
    return current_count <= limit


# ---------- 缓存操作 ----------

async def cache_result(redis: Redis, key: str, value: Any, expire: int = 3600) -> None:
    """缓存任意可序列化的结果，默认 1 小时过期。"""
    await set_json(redis, key, {"data": value}, expire=expire)


async def invalidate_cache(redis: Redis, pattern: str) -> int:
    """按 glob 模式批量删除缓存 key，返回删除数量。

    示例：await invalidate_cache(redis, "user:123:*")
    """
    keys = await redis.keys(pattern)
    if not keys:
        return 0
    count = await redis.delete(*keys)
    logger.info("cache_invalidated", pattern=pattern, count=count)
    return count
```

- [ ] **Step 2: 验证语法**

```bash
uv run python -c "from app.cache.operations import get, set, get_json, set_json, set_session, get_session, check_rate_limit, cache_result, invalidate_cache; print('operations.py 语法正确')"
```

预期输出：`operations.py 语法正确`

- [ ] **Step 3: 提交**

```bash
git add app/cache/operations.py
git commit -m "feat: 添加 app/cache/operations.py 业务操作封装"
```

---

## Task 5: 扩展 app/core/config.py（多 LLM 供应商配置）

**Files:**

- Modify: `app/core/config.py:112-263`

- [ ] **Step 1: 在 `Settings.__init__` 末尾（`apply_environment_settings()` 调用之前）添加以下字段**

在 `app/core/config.py` 第 219 行（`self.apply_environment_settings()` 之前）插入：

```python
        # LLM 供应商配置
        self.LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")  # openai | claude | minimax | gemini
        self.ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
        self.MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
        self.MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")
        self.GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

        # JWT 补充配置（与现有 JWT_ACCESS_TOKEN_EXPIRE_DAYS 对齐）
        self.ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
        self.REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

        # CORS（别名，兼容 ALLOWED_ORIGINS）
        cors_env = os.getenv("CORS_ORIGINS", "")
        if cors_env:
            self.CORS_ORIGINS = parse_list_from_env("CORS_ORIGINS", ["http://localhost:3000"])
        else:
            self.CORS_ORIGINS = self.ALLOWED_ORIGINS
```

- [ ] **Step 2: 验证配置加载**

```bash
uv run python -c "
from app.core.config import settings
print('LLM_PROVIDER:', settings.LLM_PROVIDER)
print('CORS_ORIGINS:', settings.CORS_ORIGINS)
print('config.py 扩展验证通过')
"
```

预期输出：

```
LLM_PROVIDER: openai
CORS_ORIGINS: ['*']
config.py 扩展验证通过
```

- [ ] **Step 3: 提交**

```bash
git add app/core/config.py
git commit -m "feat: config.py 添加多 LLM 供应商及 CORS_ORIGINS 配置"
```

---

## Task 6: 扩展 LLM Registry（Claude / MiniMax / Gemini 支持）

**Files:**

- Modify: `app/services/llm/registry.py`

- [ ] **Step 1: 重写 `app/services/llm/registry.py`**

```python
# app/services/llm/registry.py
"""LLM 模型注册表：按供应商动态构建，支持 openai / claude / minimax / gemini。"""

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import SecretStr

from app.core.config import (
    Environment,
    settings,
)
from app.core.logging import logger


def _build_openai_llms() -> list[dict[str, Any]]:
    """构建 OpenAI 模型列表。"""
    from langchain_openai import ChatOpenAI

    api_key = SecretStr(settings.OPENAI_API_KEY)
    token_limit: dict[str, Any] = {"max_completion_tokens": settings.MAX_TOKENS}
    return [
        {
            "name": "gpt-4o-mini",
            "llm": ChatOpenAI(model="gpt-4o-mini", api_key=api_key, model_kwargs=token_limit),
        },
        {
            "name": "gpt-4o",
            "llm": ChatOpenAI(
                model="gpt-4o",
                api_key=api_key,
                model_kwargs=token_limit,
                top_p=0.95 if settings.ENVIRONMENT == Environment.PRODUCTION else 0.8,
            ),
        },
    ]


def _build_claude_llms() -> list[dict[str, Any]]:
    """构建 Anthropic Claude 模型列表。"""
    from langchain_anthropic import ChatAnthropic

    api_key = SecretStr(settings.ANTHROPIC_API_KEY)
    return [
        {
            "name": "claude-haiku-4-5",
            "llm": ChatAnthropic(
                model="claude-haiku-4-5-20251001",
                api_key=api_key,
                max_tokens=settings.MAX_TOKENS,
                temperature=settings.DEFAULT_LLM_TEMPERATURE,
            ),
        },
        {
            "name": "claude-sonnet-4-5",
            "llm": ChatAnthropic(
                model="claude-sonnet-4-5",
                api_key=api_key,
                max_tokens=settings.MAX_TOKENS,
                temperature=settings.DEFAULT_LLM_TEMPERATURE,
            ),
        },
    ]


def _build_minimax_llms() -> list[dict[str, Any]]:
    """构建 MiniMax 模型列表（OpenAI 兼容接口）。"""
    from langchain_openai import ChatOpenAI

    api_key = SecretStr(settings.MINIMAX_API_KEY)
    return [
        {
            "name": "minimax-text-01",
            "llm": ChatOpenAI(
                model="MiniMax-Text-01",
                api_key=api_key,
                base_url=settings.MINIMAX_BASE_URL,
                max_tokens=settings.MAX_TOKENS,
                temperature=settings.DEFAULT_LLM_TEMPERATURE,
            ),
        },
        {
            "name": "minimax-m1",
            "llm": ChatOpenAI(
                model="MiniMax-M1",
                api_key=api_key,
                base_url=settings.MINIMAX_BASE_URL,
                max_tokens=settings.MAX_TOKENS,
            ),
        },
    ]


def _build_gemini_llms() -> list[dict[str, Any]]:
    """构建 Google Gemini 模型列表。"""
    from langchain_google_genai import ChatGoogleGenerativeAI

    return [
        {
            "name": "gemini-2.0-flash",
            "llm": ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                google_api_key=settings.GOOGLE_API_KEY,
                max_output_tokens=settings.MAX_TOKENS,
                temperature=settings.DEFAULT_LLM_TEMPERATURE,
            ),
        },
        {
            "name": "gemini-2.5-pro",
            "llm": ChatGoogleGenerativeAI(
                model="gemini-2.5-pro-preview-05-06",
                google_api_key=settings.GOOGLE_API_KEY,
                max_output_tokens=settings.MAX_TOKENS,
            ),
        },
    ]


_BUILDERS = {
    "openai": _build_openai_llms,
    "claude": _build_claude_llms,
    "minimax": _build_minimax_llms,
    "gemini": _build_gemini_llms,
}


class LLMRegistry:
    """按 LLM_PROVIDER 动态构建模型注册表。"""

    def __init__(self) -> None:
        provider = settings.LLM_PROVIDER.lower()
        builder = _BUILDERS.get(provider)
        if builder is None:
            raise ValueError(
                f"不支持的 LLM_PROVIDER: '{provider}'。可选值：{list(_BUILDERS.keys())}"
            )
        self.LLMS: list[dict[str, Any]] = builder()
        logger.info("llm_registry_initialized", provider=provider, models=[e["name"] for e in self.LLMS])

    def get(self, model_name: str, **kwargs) -> BaseChatModel:
        """按名称获取 LLM，支持 kwargs 覆盖默认配置。"""
        entry = next((e for e in self.LLMS if e["name"] == model_name), None)
        if not entry:
            available = ", ".join(e["name"] for e in self.LLMS)
            raise ValueError(f"模型 '{model_name}' 不存在。可用模型：{available}")
        if kwargs:
            logger.debug("llm_custom_args", model=model_name, args=list(kwargs.keys()))
            # 复用现有实例类型重新构造
            return entry["llm"].__class__(
                model=model_name,
                **{k: v for k, v in entry["llm"].__dict__.items() if not k.startswith("_")},
                **kwargs,
            )
        return entry["llm"]

    def get_all_names(self) -> list[str]:
        """返回所有已注册模型名称。"""
        return [e["name"] for e in self.LLMS]

    def get_default(self) -> BaseChatModel:
        """返回配置的默认模型（DEFAULT_LLM_MODEL）。"""
        name = settings.DEFAULT_LLM_MODEL
        try:
            return self.get(name)
        except ValueError:
            logger.warning("default_model_not_found_using_first", requested=name)
            return self.LLMS[0]["llm"]


# 全局单例（由 service.py 使用）
llm_registry = LLMRegistry()
```

- [ ] **Step 2: 验证 registry 可加载（不需要实际 API key）**

```bash
LLM_PROVIDER=openai OPENAI_API_KEY=test uv run python -c "
from app.services.llm.registry import LLMRegistry
r = LLMRegistry()
print('registry models:', r.get_all_names())
print('LLM registry 验证通过')
"
```

预期输出：`registry models: ['gpt-4o-mini', 'gpt-4o']` + `LLM registry 验证通过`

- [ ] **Step 3: 提交**

```bash
git add app/services/llm/registry.py
git commit -m "feat: LLM registry 扩展 claude/minimax/gemini 多供应商支持"
```

---

## Task 7: 初始化 Next.js 前端

**Files:**

- Create: `frontend/` (整个目录)

- [ ] **Step 1: 初始化 Next.js 项目**

```bash
cd <PROJECT_DIR>
npx create-next-app@latest frontend \
  --typescript \
  --tailwind \
  --app \
  --no-src-dir \
  --import-alias "@/*" \
  --yes
```

预期输出：`Success! Created frontend at .../frontend`

- [ ] **Step 2: 安装 shadcn/ui**

```bash
cd frontend
npx shadcn@latest init --defaults
```

预期：生成 `components.json`，`tailwind.config.ts` 更新

- [ ] **Step 3: 安装 shadcn 组件**

```bash
cd frontend
npx shadcn@latest add button input form card label toast
```

预期：`components/ui/` 下出现对应组件文件

- [ ] **Step 4: 安装前端依赖**

```bash
cd frontend
npm install axios zustand
```

预期：`node_modules/axios` 和 `node_modules/zustand` 存在

- [ ] **Step 5: 验证前端构建**

```bash
cd frontend
npm run build
```

预期：`Build completed successfully` 无报错

---

## Task 8: 创建前端 API 客户端

**Files:**

- Create: `frontend/lib/api/client.ts`

- Create: `frontend/lib/api/auth.ts`

- [ ] **Step 1: 创建 `frontend/lib/api/client.ts`**

```typescript
// frontend/lib/api/client.ts
import axios, { AxiosInstance, AxiosError } from 'axios'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

// 请求拦截器：自动带上 Authorization: Bearer token
apiClient.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
  }
  return config
})

// 响应拦截器：401 自动跳转登录页，统一错误结构
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('access_token')
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default apiClient
```

- [ ] **Step 2: 创建 `frontend/lib/api/auth.ts`**

```typescript
// frontend/lib/api/auth.ts
import apiClient from './client'

export interface AuthResponse {
  access_token: string
  token_type: string
}

export interface User {
  id: number
  email: string
  username?: string
  created_at: string
}

export const login = async (email: string, password: string): Promise<AuthResponse> => {
  const form = new URLSearchParams()
  form.append('username', email)
  form.append('password', password)

  const response = await apiClient.post<AuthResponse>('/api/v1/auth/login', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return response.data
}

export const register = async (email: string, password: string): Promise<User> => {
  const response = await apiClient.post<User>('/api/v1/auth/register', { email, password })
  return response.data
}

export const logout = async (): Promise<void> => {
  await apiClient.post('/api/v1/auth/logout')
}

export const getMe = async (): Promise<User> => {
  const response = await apiClient.get<User>('/api/v1/auth/me')
  return response.data
}
```

- [ ] **Step 3: 验证 TypeScript 类型检查**

```bash
cd frontend
npx tsc --noEmit
```

预期：无报错输出

- [ ] **Step 4: 提交**

```bash
cd <PROJECT_DIR>
git add frontend/lib/api/
git commit -m "feat: 添加前端 Axios API 客户端和认证 API"
```

---

## Task 9: 创建前端 Zustand 认证状态管理

**Files:**

- Create: `frontend/lib/store/auth.ts`

- [ ] **Step 1: 创建 `frontend/lib/store/auth.ts`**

```typescript
// frontend/lib/store/auth.ts
import { create } from 'zustand'
import { login as apiLogin, logout as apiLogout, getMe, User } from '@/lib/api/auth'

interface AuthState {
  user: User | null
  token: string | null
  isLoading: boolean
  error: string | null

  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  fetchMe: () => Promise<void>
  clearError: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: typeof window !== 'undefined' ? localStorage.getItem('access_token') : null,
  isLoading: false,
  error: null,

  login: async (email, password) => {
    set({ isLoading: true, error: null })
    try {
      const { access_token } = await apiLogin(email, password)
      localStorage.setItem('access_token', access_token)
      const user = await getMe()
      set({ user, token: access_token, isLoading: false })
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '登录失败'
      set({ error: message, isLoading: false })
      throw err
    }
  },

  logout: async () => {
    set({ isLoading: true })
    try {
      await apiLogout()
    } finally {
      localStorage.removeItem('access_token')
      set({ user: null, token: null, isLoading: false })
    }
  },

  fetchMe: async () => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
    if (!token) return
    set({ isLoading: true })
    try {
      const user = await getMe()
      set({ user, isLoading: false })
    } catch {
      localStorage.removeItem('access_token')
      set({ user: null, token: null, isLoading: false })
    }
  },

  clearError: () => set({ error: null }),
}))
```

- [ ] **Step 2: 验证 TypeScript 类型检查**

```bash
cd frontend
npx tsc --noEmit
```

预期：无报错

- [ ] **Step 3: 提交**

```bash
cd <PROJECT_DIR>
git add frontend/lib/store/
git commit -m "feat: 添加 Zustand 认证状态管理"
```

---

## Task 10: 创建部署配置文件

**Files:**

- Create: `Procfile`

- Create: `infra/docker-compose.yml`

- [ ] **Step 1: 创建 `Procfile`**

```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

- [ ] **Step 2: 创建 `infra/docker-compose.yml`**

```yaml
# infra/docker-compose.yml — 本地开发用，包含前端服务
# 与根目录 docker-compose.yml 的区别：添加了前端 + 简化了 Grafana/Prometheus
version: '3.8'

services:
  # PostgreSQL 16（含 pgvector 扩展）
  postgres:
    image: pgvector/pgvector:pg16
    platform: linux/amd64
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-mydb}
      POSTGRES_USER: ${POSTGRES_USER:-myuser}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-mypassword}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-myuser} -d ${POSTGRES_DB:-mydb}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  # Redis/Valkey 7-alpine 兼容缓存
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  # 后端 FastAPI
  backend:
    build:
      context: ..
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    env_file:
      - ../.env
    environment:
      POSTGRES_HOST: postgres
      VALKEY_HOST: redis
      APP_ENV: development
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ../app:/app/app
      - ../logs:/app/logs
    restart: on-failure

  # 前端 Next.js
  frontend:
    build:
      context: ../frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
    depends_on:
      - backend
    restart: on-failure

volumes:
  postgres_data:
  redis_data:
```

- [ ] **Step 3: 提交**

```bash
git add Procfile infra/docker-compose.yml
git commit -m "feat: 添加 Procfile 和 infra/docker-compose.yml 部署配置"
```

---

## Task 11: 更新环境变量配置文件

**Files:**

- Modify: `.env.example`

- Create: `frontend/.env.example`

- [ ] **Step 1: 替换 `.env.example`**

```bash
# .env.example — 所有环境变量说明（带中文注释）

# ===== 应用基础 =====
APP_ENV=development                    # 环境：development | staging | production
PROJECT_NAME="My AI Agent"            # 项目名称
VERSION=1.0.0
DEBUG=true

# ===== API 配置 =====
API_V1_STR=/api/v1
ALLOWED_ORIGINS="http://localhost:3000,https://v0.dev"  # 允许的跨域来源

# ===== 数据库 PostgreSQL =====
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=mydb
POSTGRES_USER=myuser
POSTGRES_PASSWORD=mypassword
POSTGRES_POOL_SIZE=10                  # 连接池大小
POSTGRES_MAX_OVERFLOW=20               # 超出连接池时最大额外连接数

# ===== Redis / Valkey 缓存 =====
VALKEY_HOST=localhost                  # 留空则使用内存缓存
VALKEY_PORT=6379
VALKEY_DB=0
VALKEY_PASSWORD=                       # 无密码则留空
VALKEY_MAX_CONNECTIONS=10
CACHE_TTL_SECONDS=3600                 # 默认缓存过期时间（秒）

# ===== LLM 供应商 =====
LLM_PROVIDER=claude                    # openai | claude | minimax | gemini
DEFAULT_LLM_MODEL=claude-sonnet-4-5    # 默认使用的模型名称
DEFAULT_LLM_TEMPERATURE=0.2
MAX_TOKENS=4096

# OpenAI（LLM_PROVIDER=openai 时使用）
OPENAI_API_KEY=

# Anthropic Claude（LLM_PROVIDER=claude 时使用）
ANTHROPIC_API_KEY=

# MiniMax（LLM_PROVIDER=minimax 时使用）
MINIMAX_API_KEY=
MINIMAX_BASE_URL=https://api.minimax.chat/v1

# Google Gemini（LLM_PROVIDER=gemini 时使用）
GOOGLE_API_KEY=

# ===== JWT 认证 =====
JWT_SECRET_KEY=change-me-in-production   # 生产环境必须替换为随机长字符串
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_DAYS=30
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# ===== Langfuse 可观测性（可选）=====
LANGFUSE_TRACING_ENABLED=false
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com

# ===== 限流 =====
RATE_LIMIT_DEFAULT="200 per day,50 per hour"
RATE_LIMIT_CHAT="30 per minute"
RATE_LIMIT_LOGIN="20 per minute"

# ===== 日志 =====
LOG_LEVEL=DEBUG
LOG_FORMAT=console                     # console | json

# ===== 会话命名 =====
SESSION_NAMING_ENABLED=true
LONG_TERM_MEMORY_COLLECTION_NAME=longterm_memory
```

- [ ] **Step 2: 创建 `frontend/.env.example`**

```bash
# frontend/.env.example
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- [ ] **Step 3: 提交**

```bash
git add .env.example frontend/.env.example
git commit -m "feat: 更新 .env.example 包含所有配置项"
```

---

## Task 12: 创建项目 CLAUDE.md

**Files:**

- Modify: `CLAUDE.md` (替换模板原有内容)

- [ ] **Step 1: 替换 `CLAUDE.md`**

```markdown
# CLAUDE.md — 项目规则

## 语言规则
所有回复、注释、计划、任务说明必须使用**中文**。
代码中的变量名、函数名、类名保持**英文**。

## 技术栈

### 后端
- Python 3.13 + uv（包管理器，不使用 pip）
- FastAPI + uvicorn（ASGI 服务器）
- LangGraph + LangChain（AI Agent 框架）
- SQLModel + asyncpg（ORM + 异步 PostgreSQL 驱动）
- Alembic（数据库迁移，不手动写 SQL）
- redis-py asyncio（Redis 客户端，非 aioredis）
- structlog（结构化日志，非 print）
- Prometheus + Grafana（监控）

### 前端
- Next.js 14 App Router + TypeScript
- Tailwind CSS + shadcn/ui
- Zustand（全局状态管理）
- Axios（HTTP 客户端）

### 部署
- 后端：Railway（Procfile）
- 前端：Vercel
- 数据库：Supabase（PostgreSQL + pgvector）
- 缓存：Upstash Redis
- DNS/CDN：Cloudflare

## 目录结构规则

```
app/
├── api/v1/          # FastAPI 路由，每个 domain 一个文件
├── cache/           # Redis 操作（新业务代码放这里）
│   ├── client.py    # 连接管理 + get_redis() 依赖注入
│   └── operations.py # session/rate_limit/cache 业务操作
├── core/
│   ├── cache.py     # ValkeyCacheService（内部使用，不直接在业务层调用）
│   ├── config.py    # Settings 全局配置
│   ├── langgraph/   # LangGraph 图定义和工具
│   └── ...          # 日志、限流、中间件、可观测性
├── db/
│   ├── base.py      # UUIDModel（新模型的基类）
│   └── session.py   # get_db() 异步依赖 + get_sync_session()
├── models/
│   ├── base.py      # BaseModel（现有 User/Session 用，保留）
│   ├── user.py      # User model（int id）
│   └── session.py   # ChatSession model
├── schemas/         # Pydantic request/response schemas
├── services/
│   ├── database.py  # DatabaseService（同步，保留）
│   └── llm/         # LLM registry + service
└── utils/           # 无状态工具函数
```

## 后端分层规则
- `api/v1/` 只做请求解析、参数校验、调用 service、返回响应。不写业务逻辑。
- `services/` 写业务逻辑，不直接操作数据库或 Redis。
- `services/database.py` 写数据库操作。
- `app/cache/operations.py` 写 Redis 业务操作。
- `models/` 只定义 SQLModel 表结构，不写业务方法（除 User.verify_password/hash_password）。

## 数据库规则
- 所有新表模型继承 `app.db.base.UUIDModel`（UUID 主键）。
- 现有 User / ChatSession 保持 int/str 主键，不迁移。
- 迁移用 `alembic revision --autogenerate -m "描述"` 生成，不手写 SQL。
- 异步端点用 `get_db()`（AsyncSession）。Celery 任务用 `get_sync_session()`。
- 连接池：pool_size=10，max_overflow=20。

## Redis 使用规则
- 业务代码通过 `Depends(get_redis)` 获取客户端，调用 `app.cache.operations` 中的函数。
- 直接使用 `app/core/cache.py` 的 `cache_service` 仅限内部（如 API 响应缓存）。
- key 命名格式：`{prefix}:{identifier}`，如 `session:123`、`rate:user:456:chat`。
- 所有 key 必须设置过期时间（TTL），严禁永不过期的 key。

## LLM 供应商规则
- 通过 `LLM_PROVIDER` 环境变量切换：`openai` | `claude` | `minimax` | `gemini`。
- 在 `app/services/llm/registry.py` 中添加新模型，不在业务代码中直接实例化 LLM。
- 默认模型由 `DEFAULT_LLM_MODEL` 指定，调用 `llm_registry.get_default()`。
- 生产环境使用 Claude Sonnet 或 GPT-4o，开发调试用 Haiku/GPT-4o-mini。

## 认证规则
- JWT 存储在 localStorage（前端），Authorization: Bearer header（请求）。
- 后端用 `JWT_SECRET_KEY` 签发，`JWT_ACCESS_TOKEN_EXPIRE_DAYS` 控制有效期。
- Redis Session 存储（`set_session` / `get_session`）用于登出黑名单。
- 注册时密码用 `User.hash_password()`（bcrypt）哈希，验证用 `User.verify_password()`。

## 前后端交互规则
- 前端统一通过 `frontend/lib/api/client.ts` 的 Axios 实例请求后端。
- 所有 API 路径前缀为 `/api/v1/`。
- 后端 CORS 允许来源在 `ALLOWED_ORIGINS` / `CORS_ORIGINS` 环境变量配置。
- 前端用 `NEXT_PUBLIC_API_URL` 指向后端地址（本地 `http://localhost:8000`）。

## 部署规则
- **本地开发**：`infra/docker-compose.yml`（含 postgres + redis + backend + frontend）。
- **后端生产**：Railway 读取 `Procfile`，环境变量在 Railway Dashboard 设置。
- **前端生产**：Vercel 自动检测 Next.js，设置 `NEXT_PUBLIC_API_URL` 为 Railway 后端 URL。
- **数据库生产**：Supabase PostgreSQL（支持 pgvector），在 `POSTGRES_*` 变量中配置连接串。
- **缓存生产**：Upstash Redis，在 `VALKEY_HOST/PORT/PASSWORD` 中配置。

## 包管理规则
- 使用 `uv add <package>` 安装依赖，不使用 `pip install`。
- 运行脚本使用 `uv run python ...`。
- 不提交 `.venv/` 目录。

## 迭代规则
- 新功能先写 failing test，再写实现（TDD）。
- 每完成一个小功能即提交（小步提交）。
- 修改配置后更新 `.env.example`，保持文档同步。
- PR 前运行 `uv run ruff check app/` 和 `npx tsc --noEmit`。
```

- [ ] **Step 2: 提交**

```bash
git add CLAUDE.md
git commit -m "docs: 替换为项目专属 CLAUDE.md 规则文件"
```

---

## Task 13: 验证整体项目

- [ ] **Step 1: 后端语法全量检查**

```bash
uv run ruff check app/
```

预期：无 error 输出（warning 可忽略）

- [ ] **Step 2: 前端类型检查**

```bash
cd frontend && npx tsc --noEmit
```

预期：无报错

- [ ] **Step 3: 检查所有文件到位**

```bash
ls app/db/session.py app/db/base.py app/cache/client.py app/cache/operations.py Procfile infra/docker-compose.yml .env.example frontend/.env.example CLAUDE.md
```

预期：所有文件均存在（无 `No such file` 报错）

- [ ] **Step 4: 最终提交（如有未提交内容）**

```bash
git status
# 检查无遗漏，全部已提交
```

---

## 启动命令（完成后）

### 本地开发（Docker Compose）

```bash
# 1. 复制并填写环境变量
cp .env.example .env
# 编辑 .env 填写 API keys

# 2. 启动所有服务
cd infra && docker compose up -d

# 3. 运行数据库迁移
docker exec -it <backend-container> uv run alembic upgrade head

# 4. 访问
# 后端 API: http://localhost:8000/docs
# 前端:     http://localhost:3000
# 健康检查: http://localhost:8000/health
```

### 不用 Docker 的本地开发

```bash
# 后端
cp .env.example .env  # 填写配置
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# 前端（新终端）
cd frontend
cp .env.example .env.local
npm run dev
```

### 验证方法

```bash
# 检查后端健康
curl http://localhost:8000/health

# 检查 API 文档
open http://localhost:8000/docs

# 检查前端
open http://localhost:3000
```
