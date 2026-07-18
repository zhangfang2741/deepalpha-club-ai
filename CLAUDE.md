# CLAUDE.md — deepalpha-club-ai 项目规则

## 语言规则
所有回复、注释、计划、任务说明必须使用**中文**。
代码中的变量名、函数名、类名保持**英文**。

## 完整技术栈

### 后端
- Python 3.13 + **uv**（包管理器，禁止使用 pip）
- FastAPI + uvicorn（ASGI 服务器，生产用 uvloop）
- LangGraph + LangChain（AI Agent 框架，`langgraph-checkpoint-postgres` 做检查点）
- SQLModel + asyncpg（ORM + 异步 PostgreSQL 驱动）；同步场景用 psycopg
- Alembic（数据库迁移，不手动写 SQL）
- redis-py asyncio（Redis 客户端，非 aioredis）
- structlog（结构化日志，禁止使用 print）+ asgi-correlation-id（request_id 贯穿日志）
- tenacity（重试逻辑）
- Prometheus + Grafana（监控）+ Langfuse（LLM 可观测性）
- mem0ai（长期记忆向量存储，pgvector 后端）
- LLM SDK：langchain-openai / langchain-anthropic / langchain-google-genai
- 行情/财务数据源：FMP（financialmodelingprep，主）、yfinance、akshare、SEC EDGAR、DuckDuckGo（ddgs）

### 数据源与 API Key
- **FMP**（`FMP_API_KEY`）：估值、机构持仓、分析师、财报电话会、SEC filings 等核心数据源。
- **NEWS_API_KEY**：新闻抓取（analyzer/news_client）。
- 各 LLM 供应商 key：`OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` / `MINIMAX_API_KEY`。

### 前端
- **Next.js 16 App Router**（非 14）+ React 19 + TypeScript
  - ⚠️ 见 `frontend/AGENTS.md`：本仓库 Next.js 版本较新，API/约定可能与训练数据不同，改动前先查 `node_modules/next/dist/docs/`。
- Tailwind CSS + shadcn/ui（`components/ui/`）
- lucide-react（图标）
- lightweight-charts（K 线/技术分析图表）
- Zustand（全局状态管理，`lib/store/`）
- Axios（HTTP 客户端，统一通过 `lib/api/client.ts` 实例）

### 部署
- 后端：Railway（`Procfile`）
- 前端：Vercel
- 数据库：Supabase（PostgreSQL + pgvector）
- 缓存：Upstash Redis（`VALKEY_HOST/PORT/PASSWORD` 配置）
- DNS/CDN：Cloudflare

## 目录结构

> ⚠️ 本项目已从「AI Agent 模板」发展为**美股投研平台**：一个 LangGraph 聊天 Agent + 十余个投研分析模块（估值、技术分析、机构动向、产业图谱、因子探索等）。每个模块通常横跨 `api/v1/*` ↔ `services/*` ↔ `schemas/*` ↔ 前端 `app/*` + `components/*` + `lib/api/*`。

```
deepalpha-club-ai/
├── app/
│   ├── api/v1/               # FastAPI 路由（每个 domain 一个文件，见「功能模块地图」）
│   │   ├── api.py            # 汇总所有子路由的 api_router + /health
│   │   └── auth/             # 认证路由（routes.py / dependencies.py）
│   ├── cache/                # Redis 业务操作（新业务代码放这里）
│   │   ├── client.py         # 连接管理 + get_redis() 依赖注入
│   │   ├── operations.py     # session/rate_limit/cache 业务操作
│   │   └── *_cache.py        # 各模块专用缓存（etf/valuation/fear_greed 等）
│   ├── core/
│   │   ├── cache.py          # ValkeyCacheService（内部/lifespan 使用）
│   │   ├── config.py         # Settings 全局配置（所有环境变量入口）
│   │   ├── langgraph/        # LangGraph 图定义（graph.py）+ Agent 工具（tools/）
│   │   ├── prompts/          # 系统提示词（system.md / session_title.md）
│   │   ├── limiter.py        # slowapi 限流
│   │   ├── logging.py        # structlog 日志
│   │   ├── metrics.py        # Prometheus 指标
│   │   ├── middleware.py     # ASGI 中间件（日志上下文/指标/性能分析）
│   │   └── observability.py  # Langfuse 可观测性
│   ├── db/                   # 数据库 session 管理
│   │   ├── base.py           # UUIDModel（新模型的基类）
│   │   └── session.py        # get_db() 异步依赖 + get_sync_session() + sync_engine
│   ├── models/               # SQLModel 表模型
│   │   ├── base.py           # BaseModel（现有 User/ChatSession 用，保留）
│   │   ├── user.py           # User（int id，bcrypt）
│   │   ├── session.py        # ChatSession（str id）
│   │   ├── thread.py         # Thread
│   │   ├── analysis.py       # 结构性投资六层分析记录
│   │   ├── signal_snapshot.py# 机构信号快照
│   │   ├── factor_*.py       # 因子探索（category/skill/run）
│   │   └── graph_*.py / finkg_triple.py  # 产业图谱实体/事实/来源/三元组
│   ├── schemas/              # Pydantic request/response schemas（每模块一个）
│   ├── services/             # 业务逻辑（不直接碰 DB/Redis，见分层规则）
│   │   ├── database.py       # DatabaseService（同步，保留）
│   │   ├── memory.py         # mem0 长期记忆
│   │   ├── llm/              # registry.py（多供应商注册表）+ service.py（重试+fallback）
│   │   ├── analyzer/         # 结构性投资分析（fmp_client/sec_edgar/news_client）
│   │   ├── valuation/        # GICS 行业 PE 估值 z-score
│   │   ├── etf/              # ETF 资金流热力图 + 偏离度
│   │   ├── fear_greed.py     # 恐慌贪婪指数
│   │   ├── industry_panic/   # 行业 RSI 情绪
│   │   ├── chan/ ichimoku/ wyckoff/   # 缠论 / 一目均衡表 / 威科夫技术分析
│   │   ├── analyst_upgrade/  # 分析师目标价上调（sp500 / nasdaq100）
│   │   ├── institutional_signals/    # 13F 机构建仓信号
│   │   ├── sec_filings/      # SEC 文件 + 公司画像
│   │   ├── transcript_ai.py / motley_fool.py  # 财报电话会转录 + AI 翻译
│   │   ├── graph/            # 产业图谱（fmp/sec 抓取 + pipeline + finreflect KG 抽取）
│   │   ├── skills/           # 因子探索：LLM 生成代码 → AST 校验 → 沙箱执行
│   │   ├── research.py       # 深度行业研究
│   │   └── session_naming.py # 会话自动命名
│   ├── utils/                # 无状态工具（auth.py / sanitization.py）
│   └── main.py               # FastAPI 入口 + lifespan（启动迁移/预热 Agent/mem0/种子）
├── alembic/versions/         # 数据库迁移（自动生成）
├── tests/                    # pytest（asyncio_mode=auto，见「测试规则」）
├── evals/                    # LLM 评估框架（make eval）
├── scripts/                  # 运维脚本（docker/seed/set_env）
├── docs/                     # 架构/配置/认证等文档 + superpowers/plans（实施计划归档）
├── frontend/                 # Next.js 16 前端（详见 frontend/AGENTS.md）
│   ├── app/                  # App Router 页面（每个投研模块一个目录）
│   ├── components/           # 按模块分目录 + ui/（shadcn） + layout/（TopNav/DashboardShell）
│   ├── lib/
│   │   ├── api/              # 每模块一个 Axios 封装 + client.ts + auth.ts
│   │   ├── store/            # Zustand（auth/etf/fear_greed/skills）
│   │   └── constants/        # 前端常量（阈值/配色）
│   └── Dockerfile
├── infra/docker-compose.yml  # 本地开发（含前端）
├── docker-compose.yml        # 完整监控栈（Prometheus + Grafana）
├── Dockerfile / Procfile     # 后端 Docker 镜像 / Railway 部署
├── Makefile                  # 常用命令入口（见「常用命令」）
├── pyproject.toml            # uv 项目配置 + ruff/pyright 配置
└── .env.example              # 环境变量模板

```

## 功能模块地图（API 前缀 ↔ 前端页面）

后端子路由在 `app/api/v1/api.py` 汇总，均挂载在 `/api/v1` 下。前端导航结构见 `frontend/components/layout/TopNav.tsx`。

| 模块 | 后端前缀 | 前端页面 | 说明 |
|------|----------|----------|------|
| 认证 | `/auth` | `/`（登录） | JWT 登录 + Chat session token |
| AI 对话 | `/chatbot` | `/chat` | LangGraph 流式聊天 Agent |
| 因子探索 | `/skills` | `/skill-generator` | LLM 生成因子代码 → 沙箱执行 |
| 恐慌指数 | `/fear-greed` | `/fear-greed` | 市场恐慌贪婪指数 |
| 行业恐慌 | `/industry-panic` | `/industry-panic` | 各 GICS 行业 ETF 的 RSI 情绪 |
| ETF 资金流 | `/etf` | `/etf` | 资金流热力图 + 偏离度 |
| 行业估值 | `/valuation` | （并入行业恐慌页） | GICS 行业 PE z-score |
| 缠论 | `/chan` | `/chan` | 缠论分笔/中枢/背驰 |
| 威科夫 | `/wyckoff` | `/wyckoff` | Wyckoff 阶段/事件 |
| 一目均衡表 | `/ichimoku` | `/ichimoku` | Ichimoku 云图信号 |
| 分析师上调 | `/analyst-upgrades` | `/analyst-upgrades` | 目标价上调榜（SP500/Nasdaq100） |
| 机构信号 | `/institutional-signals` | `/institutional-signals` | 13F 机构建仓榜 |
| 行业研究 | `/research` | `/industry-research` | 深度行业研究 |
| 企业研究 | `/sec` | `/company-research` | SEC 文件 + 公司画像 |
| 产业图谱 | `/supply-chain` | `/supply-chain` | 供应链知识图谱 |
| 财报电话会 | `/transcripts` | `/(dashboard)/transcripts` | 转录 + AI 中文翻译 |
| 结构性分析 | `/analysis` | `/analysis` | 结构性投资六层分析框架 |

> 新增一个投研模块时，通常需同步落地五处：`app/api/v1/<mod>.py`、`app/services/<mod>/`、`app/schemas/<mod>.py`、前端 `app/<mod>/page.tsx` + `lib/api/<mod>.ts`，并在 `api.py`、`TopNav.tsx` 注册。

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
- 在 `app/services/llm/registry.py` 的 `_build_*_llms()` 中添加新模型，不在业务代码中直接实例化 LLM。
- 各供应商实际注册的模型：
  - `openai`：`gpt-4o-mini`、`gpt-4o`
  - `claude`：`claude-haiku-4-5`、`claude-sonnet-4-5`、`claude-sonnet-4-6`
  - `gemini`：`gemini-2.0-flash`、`gemini-2.5-pro`
  - `minimax`：`minimax-text-01`、`minimax-m1`
  - 特殊：当 `LLM_PROVIDER=claude` 且 `ANTHROPIC_BASE_URL` 指向 MiniMax 兼容接口时，自动改用 `MiniMax-M2.7`。
- 默认模型由 `DEFAULT_LLM_MODEL` 指定，调用 `llm_registry.get_default()`（找不到回退到列表第一个）。
- 生产环境使用 Claude Sonnet 或 GPT-4o，开发调试用 Haiku/gpt-4o-mini。
- 所有 LLM 调用通过 `llm_service.call()` 进行，自动包含重试和 fallback。

## 因子探索沙箱规则（app/services/skills）
- 因子代码由 LLM 流式生成（`generator.py`），**必须**先经 `ast_check.py` 做 AST 静态校验，再进入沙箱执行。
- 沙箱（`sandbox.py` / `sandbox_worker.py`）隔离运行用户/LLM 生成的代码，禁止在主进程直接 exec。
- 行情/财务数据通过 `fmp_data.py` 拉取；K 线结果缓存（`kline.py` + `app/cache`）。
- 新增可用数据字段时，需同步更新 `generator.py` 里的系统提示词说明，否则 LLM 不会使用。

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
4. 聊天走 Deep Agent：前端用 assistant-ui `useLangGraphRuntime`，`stream` 回调 POST `/api/v1/chatbot/langgraph/stream`（SSE 产出 `{event,data}` 结构化事件，渲染流式文本 + 工具调用/规划卡片），`load` 调用 `GET /api/v1/chatbot/langgraph/history` 恢复历史（含工具调用）。旧的纯文本端点 `/api/v1/chatbot/chat[/stream]` 与 `GET /api/v1/chatbot/messages` 保留向后兼容
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

## 测试规则
- 测试放在 `tests/`，结构镜像 `app/`（如 `tests/services/chan/`）。
- 使用 pytest，`asyncio_mode=auto`（async 测试无需显式 `@pytest.mark.asyncio`）。
- 慢测试用 `@pytest.mark.slow` 标记，`-m "not slow"` 可跳过。
- 运行：`uv run pytest`（全部）或 `uv run pytest tests/services/chan/ -v`（单模块）。

## 常用命令（优先用 Makefile，其默认 ENV=development）
| 目的 | 命令 |
|------|------|
| 安装依赖 | `make install`（= `uv sync` + pre-commit） |
| 本地起后端 | `make dev`（uvicorn --reload :8000） |
| 数据库迁移 | `make migration MSG="描述"` 生成；`make migrate` 应用 |
| 代码检查 | `make check`（= `ruff check .` + `pyright`）；`make format` 格式化 |
| 运行评估 | `make eval` / `make eval-quick` |
| Docker（API+DB） | `make docker-up` / `make docker-down` |
| 完整监控栈 | `make stack-up`（含 Prometheus + Grafana） |
| 前端类型检查 | `cd frontend && npx tsc --noEmit` |
| 前端开发 | `cd frontend && npm run dev` |

## 迭代规则
- 新功能先写 failing test，再写实现（TDD）。
- 每完成一个小功能即提交（小步提交）。
- 修改配置后同步更新 `.env.example` 和 `app/core/config.py`。
- 后端 PR 前运行 `make check`（ruff + pyright）；前端运行 `cd frontend && npx tsc --noEmit`。
- 提交信息用中文，遵循 `feat/fix/refactor(scope): 描述` 约定（见 git 历史）。
