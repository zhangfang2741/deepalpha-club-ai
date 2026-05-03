# CLAUDE.md — deepalpha-club-ai 项目规则

## 语言规则
所有回复、注释、计划、任务说明必须使用**中文**。
代码中的变量名、函数名、类名保持**英文**。

## 完整技术栈

### 后端
- Python 3.13 + **uv**（包管理器，禁止使用 pip）
- FastAPI + uvicorn（ASGI 服务器）
- LangGraph + LangChain（AI Agent 框架）
- SQLModel + asyncpg（ORM + 异步 PostgreSQL 驱动）
- Alembic（数据库迁移，不手动写 SQL）
- redis-py asyncio（Redis 客户端，非 aioredis）
- structlog（结构化日志，禁止使用 print）
- tenacity（重试逻辑）
- Prometheus + Grafana（监控）
- mem0ai（长期记忆向量存储）

### 前端
- Next.js 14 App Router + TypeScript
- Tailwind CSS + shadcn/ui
- Zustand（全局状态管理）
- Axios（HTTP 客户端，统一通过 lib/api/client.ts 实例）

### 部署
- 后端：Railway（`Procfile`）
- 前端：Vercel
- 数据库：Supabase（PostgreSQL + pgvector）
- 缓存：Upstash Redis（`VALKEY_HOST/PORT/PASSWORD` 配置）
- DNS/CDN：Cloudflare

## 目录结构

```
deepalpha-club-ai/
├── app/
│   ├── api/v1/               # FastAPI 路由（每个 domain 一个文件）
│   ├── cache/                # Redis 业务操作（新业务代码放这里）
│   │   ├── __init__.py
│   │   ├── client.py         # 连接管理 + get_redis() 依赖注入
│   │   └── operations.py     # session/rate_limit/cache 业务操作
│   ├── core/
│   │   ├── cache.py          # ValkeyCacheService（内部/lifespan 使用）
│   │   ├── config.py         # Settings 全局配置
│   │   ├── langgraph/        # LangGraph 图定义和工具
│   │   ├── limiter.py        # slowapi 限流
│   │   ├── logging.py        # structlog 日志
│   │   ├── metrics.py        # Prometheus 指标
│   │   ├── middleware.py     # ASGI 中间件
│   │   └── observability.py  # Langfuse 可观测性
│   ├── db/                   # 数据库 session 管理（新增）
│   │   ├── __init__.py
│   │   ├── base.py           # UUIDModel（新模型的基类）
│   │   └── session.py        # get_db() 异步依赖 + get_sync_session()
│   ├── models/               # SQLModel 表模型
│   │   ├── base.py           # BaseModel（现有 User/Session 用，保留）
│   │   ├── session.py        # ChatSession（str id）
│   │   ├── thread.py         # Thread
│   │   └── user.py           # User（int id，bcrypt）
│   ├── schemas/              # Pydantic request/response schemas
│   ├── services/
│   │   ├── database.py       # DatabaseService（同步，保留）
│   │   ├── llm/
│   │   │   ├── registry.py   # LLM 注册表（多供应商）
│   │   │   └── service.py    # LLMService（重试 + fallback）
│   │   └── memory.py         # mem0 长期记忆
│   ├── utils/                # 无状态工具函数
│   └── main.py               # FastAPI 入口 + lifespan
├── alembic/                  # 数据库迁移（自动生成）
├── docs/superpowers/plans/   # 实施计划归档
├── evals/                    # LLM 评估框架
├── frontend/                 # Next.js 前端
│   ├── app/                  # App Router 页面
│   ├── components/ui/        # shadcn/ui 组件
│   ├── lib/
│   │   ├── api/
│   │   │   ├── client.ts     # Axios 客户端实例
│   │   │   └── auth.ts       # 认证 API
│   │   └── store/
│   │       └── auth.ts       # Zustand 认证状态
│   ├── Dockerfile            # 前端 Docker 镜像
│   └── .env.example
├── infra/
│   └── docker-compose.yml    # 本地开发（含前端）
├── docker-compose.yml        # 完整监控栈（Prometheus + Grafana）
├── Dockerfile                # 后端 Docker 镜像
├── Procfile                  # Railway 部署
├── pyproject.toml            # uv 项目配置
└── .env.example              # 环境变量模板

```

## 后端分层规则
- `api/v1/` 只做请求解析、参数校验、调用 service、返回响应，不写业务逻辑。
- `services/` 写业务逻辑，不直接操作数据库或 Redis。
- `services/database.py` 写数据库操作（同步，DatabaseService）。
- `app/cache/operations.py` 写 Redis 业务操作。
- `models/` 只定义 SQLModel 表结构，不写业务方法（User.verify_password/hash_password 除外）。

## 数据库规则
- **新模型**继承 `app.db.base.UUIDModel`（UUID 主键 + created_at + updated_at）。
- **现有模型**（User / ChatSession）保持 int/str 主键，不迁移。
- 迁移命令：`uv run alembic revision --autogenerate -m "描述"`，不手写 SQL。
- **异步端点**用 `get_db()`（AsyncSession）；**Celery 任务**用 `get_sync_session()`。
- 连接池：`POSTGRES_POOL_SIZE=10`，`POSTGRES_MAX_OVERFLOW=20`。

## Redis 使用规则
- 业务代码通过 `Depends(get_redis)` 获取客户端，调用 `app.cache.operations` 中的函数。
- 直接使用 `app/core/cache.py` 的 `cache_service` 仅限内部（API 响应缓存）。
- key 命名格式：`{prefix}:{identifier}`（如 `session:123`、`rate:user:456:chat`）。
- **所有 key 必须设置 TTL**，严禁永不过期的 key。

## LLM 供应商规则
- 通过 `LLM_PROVIDER` 环境变量切换：`openai` | `claude` | `minimax` | `gemini`。
- 在 `app/services/llm/registry.py` 中添加新模型，不在业务代码中直接实例化 LLM。
- 默认模型由 `DEFAULT_LLM_MODEL` 指定，调用 `llm_registry.get_default()`。
- 生产环境使用 Claude Sonnet 或 GPT-4o，开发调试用 Haiku/GPT-4o-mini。
- 所有 LLM 调用通过 `llm_service.call()` 进行，自动包含重试和 fallback。

## 认证规则
- JWT 存储在 `localStorage`（前端），`Authorization: Bearer <token>` header（请求）。
- 后端用 `JWT_SECRET_KEY` 签发，`JWT_ACCESS_TOKEN_EXPIRE_DAYS` 控制有效期。
- Redis Session（`set_session` / `get_session`）用于登出黑名单管理。
- 密码用 `User.hash_password()`（bcrypt）哈希，验证用 `User.verify_password()`。

## 前后端交互规则
- 前端统一通过 `frontend/lib/api/client.ts` 的 Axios 实例请求后端，不直接用 fetch。
- 所有 API 路径前缀为 `/api/v1/`。
- 后端 CORS 通过 `ALLOWED_ORIGINS` / `CORS_ORIGINS` 环境变量配置。
- 前端用 `NEXT_PUBLIC_API_URL` 指向后端（本地：`http://localhost:8000`）。

## 部署规则
- **本地开发**：`cd infra && docker compose up -d`（含 postgres + redis + backend + frontend）。
- **后端生产**：Railway 读取 `Procfile`，环境变量在 Railway Dashboard 配置。
- **前端生产**：Vercel 自动检测 Next.js，设置 `NEXT_PUBLIC_API_URL` 为 Railway 后端 URL。
- **数据库生产**：Supabase PostgreSQL（支持 pgvector），配置 `POSTGRES_*` 变量。
- **缓存生产**：Upstash Redis，配置 `VALKEY_HOST/PORT/PASSWORD`。

## 包管理规则
- 安装依赖：`uv add <package>`，禁止 `pip install`。
- 运行脚本：`uv run python ...` 或 `uv run alembic ...`。
- 不提交 `.venv/` 目录。

## 日志规则
- 使用 structlog，禁止 print。
- 日志事件名用 `lowercase_underscore`（如 `"user_login_successful"`）。
- 禁止在 structlog 事件中使用 f-string，变量通过 kwargs 传递。
- 用 `logger.exception()` 代替 `logger.error()` 以保留 traceback。

## 迭代规则
- 新功能先写 failing test，再写实现（TDD）。
- 每完成一个小功能即提交（小步提交）。
- 修改配置后同步更新 `.env.example`。
- PR 前运行：`uv run ruff check app/` 和 `cd frontend && npx tsc --noEmit`。
