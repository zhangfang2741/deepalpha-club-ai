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

## 生产部署详情（当前实际配置）

### 域名规划（Cloudflare DNS）

| 子域名 | 指向 | 说明 |
|--------|------|------|
| `deepalpha.club` | Vercel（`cname.vercel-dns.com`） | 根域名，用户入口 |
| `www.deepalpha.club` | Vercel（重定向到根域名） | www 跳转 |
| `api.deepalpha.club` | Railway（`*.railway.app`） | 后端 API |

Cloudflare 代理状态：三条记录均开启橙色云朵（代理模式），SSL/TLS 加密模式设为 **Full**。

### 前端（Vercel）

- 仓库根目录：`frontend/`
- 框架：Next.js，`output: 'standalone'`（`frontend/next.config.ts`）
- 生产环境变量（在 Vercel Dashboard 配置）：
  ```
  NEXT_PUBLIC_API_URL=https://api.deepalpha.club
  ```
- 自定义域名：`deepalpha.club`、`www.deepalpha.club`

### 后端（Railway）

- 启动命令来自 `Procfile`：
  ```
  web: /app/.venv/bin/python -c "import os,uvicorn; uvicorn.run('app.main:app', host='0.0.0.0', port=int(os.environ.get('PORT',8000)))"
  ```
- 自定义域名：`api.deepalpha.club`
- 生产环境变量（在 Railway Dashboard 配置）：
  ```
  APP_ENV=production
  DEBUG=false
  LOG_FORMAT=json
  ALLOWED_ORIGINS=https://deepalpha.club,https://www.deepalpha.club
  CORS_ORIGINS=https://deepalpha.club,https://www.deepalpha.club
  POSTGRES_SSL=true
  VALKEY_SSL=true
  ```

### 数据库（Supabase）

- 提供 PostgreSQL + pgvector，配置 `POSTGRES_HOST/PORT/DB/USER/PASSWORD`
- 生产必须设置 `POSTGRES_SSL=true`

### 缓存（Upstash Redis）

- 配置 `VALKEY_HOST`（`*.upstash.io`）、`VALKEY_PASSWORD`、`VALKEY_SSL=true`

### Chat 会话认证流程

前端 Chat 使用独立的 **session token**（区别于登录的 `access_token`）：
1. 前端调用 `POST /api/v1/auth/sessions` 创建 Chat Session，返回 `session.token.access_token`
2. Session token 存储在 `localStorage`（key：`chat_session_token`）
3. 后续所有聊天请求携带 `Authorization: Bearer <session_token>`
4. `ThreadHistoryAdapter.load()` 调用 `GET /api/v1/chatbot/messages` 恢复历史
5. 清空对话：`DELETE /api/v1/chatbot/messages`，同时清除 localStorage 中的 session token

### 验证命令

```bash
# 检查后端健康
curl https://api.deepalpha.club/api/v1/health

# 验证 Cloudflare 代理（响应头含 cf-ray 即为正常）
curl -I https://deepalpha.club
```

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
