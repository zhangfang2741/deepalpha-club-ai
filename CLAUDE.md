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
| 市场状态 | `/regime` | 并入恐慌指数页(大盘) + 行业恐慌页(板块) | 三篮子 ODS/CF + HMM 逐利/观望/避险后验，写因子表；大盘级与行业级各一套 |
| 恐慌指数 | `/fear-greed` | `/fear-greed` | 市场恐慌贪婪指数 + 大盘市场状态(regime) |
| 宏观 / 行业 | `/macro` | iOS 雷达页顶部「大盘环境 › 行业 › 当日信号」三张卡片（行业卡片是下拉筛选，选了雷达只显示该行业，`SignalRadarViewModel.sectorFilter`）；自选页顶部环境横幅 | 大盘状态(regime) + 5 个驱动因素 + 未来 7 天宏观日历；行业相对强弱（`?date=` 按雷达所选日）。`/signal-radar/sector-pools`、`/sector-day` 仅为旧版 App 保留（新版 App 用气泡自带的 `sector` 在本地按行业筛选）。第一期仅美股，A 股 / 港股 `available=false` |
| 行业恐慌 | `/industry-panic` | `/industry-panic` | 各 GICS 行业 ETF 的 RSI 情绪 + 估值 + 板块状态(行业级 regime) |
| ETF 资金流 | `/etf` | `/etf` | 资金流热力图 + 偏离度 |
| 行业估值 | `/valuation` | （并入行业恐慌页） | GICS 行业 PE z-score |
| 缠论 | `/chan` | `/chan` | 缠论分笔/中枢/背驰 |
| 信号雷达 | `/signal-radar` | iOS「雷达」Tab（页面标题「市场雷达」） | 扫描各市场指数成分股跑缠论，**只陈列事实**：某天在场的全部买卖点按出现时间排（`scope=all`，新版 App；不带 scope 的旧版 App 在接口层按旧综合分截前 10）。App 用严格口径，只画已成立的买卖点（「待确认」只在雷达上方显示个数）。气泡：红买绿卖、深浅=信号强弱、大小=一二三类；由内向外越靠中心越新、互不重叠（`SectorRadarLayout.pack` 整圆一个扇区）。按行业分扇区的画法已关闭（`SignalRadarView.sectorFieldEnabled=false`，代码与测试保留）。点气泡 / 顶部卡片都是底部面板，「查看K线与结构详情」才进详情页 |
| 威科夫 | `/wyckoff` | `/wyckoff` | Wyckoff 阶段/事件 |
| 一目均衡表 | `/ichimoku` | `/ichimoku` | Ichimoku 云图信号 |
| 分析师上调 | `/analyst-upgrades` | `/analyst-upgrades` | 目标价上调榜（SP500/Nasdaq100）；`/overview/{symbol}` 为缠论 App 详情页「分析师评级」分段 |
| 基本面研究（代码内仍叫 quant_research） | `/quant-research` | 缠论 App 详情页「基本面研究」分段 | 美股五维度（估值/成长/盈利能力/动量/EPS 修正）标普500+纳斯达克100板块内百分位 → A+~F，三层下钻 + 方法说明 |
| 机构信号 | `/institutional-signals` | `/institutional-signals` | 13F 机构建仓榜 |
| 行业研究 | `/research` | `/industry-research` | 深度行业研究 |
| 企业研究 | `/sec` | `/company-research` | SEC 文件 + 公司画像 |
| 产业图谱 | `/supply-chain` | `/supply-chain` | 供应链知识图谱 |
| 财报电话会 | `/transcripts` | `/(dashboard)/transcripts` | 转录 + AI 中文翻译 |
| 结构性分析 | `/analysis` | `/analysis` | 结构性投资六层分析框架 |

> 宏观 / 行业约束（`app/services/macro`，设计见 `docs/superpowers/specs/2026-10-01-market-macro-sector-design.md`）：
> 数据来自 regime 两张因子表，由 `regime/scheduler.py` 每日重算（美股 UTC 22:45 + 启动补跑，**子进程 + 降优先级**，约 40 分钟，
> 不要改回线程池——纯 Python HMM 循环占 GIL 会拖慢 API）。驱动因素 / 日历的 FMP 调用经 `FmpClient`（全局预算）。
> 文案只描述环境，不出现买卖导向词与数据供应商 / 基金代码（`test_drivers.test_no_trading_words`）。
> 雷达行业标签（`signal_radar/sectors.py`，指数雷达与自选雷达都打；自选列表接口也带 `sector`）的行业 key 与 regime `SECTORS` 一致（有测试守护）。
> 行业池（每行业按旧综合分的前 N）只给旧版 App 的行业筛选用。

> 信号雷达扫描约束（`app/services/signal_radar`）：同一 (口径, 市场, universe) 任一时刻只跑一轮全量扫描
> ——接口与定时预热共用 `scan_lock_key` 原子锁（`acquire_lock` = SET NX EX），主动刷新有 5 分钟冷却；
> 所有扫描 / 补算 / 示例日拉 K 线共用进程级闸门 `_fetch_gate`。拉数失败（限流 / 不可用）的成分股
> 由 `_backfill` 在后台逐轮慢慢补算、补上即重写快照（响应 `pending_symbols` = 仍在补算的只数），
> 轮次号存 Redis（`incr_with_ttl`），新一轮扫描开始旧补算自动退出。免费示例日（`compute_demo_day`）同一套补算。
> 补算进度记为 Redis 标记（`signal_radar:backfill:*`，含进程 owner），进程重启后 `scheduler._resume_orphan_backfills`
> 在启动预热之后接手别的进程没补完的。**不要**绕过锁直接起全量扫描。
> **雷达只呈现事实、不做推荐**（2026-10-01 起，设计见 `docs/superpowers/specs/2026-10-01-radar-facts-top-down-design.md`）：
> 快照存每天**在场的全部信号**、按出现时间从新到旧（`order_by_time`），不打分、不截前 N、不按共振重排；
> **基本面排雷已取消**（评级只标注，`quant_filter.attach_grades` 不再剔除任何信号）。只保留定义层面的规则：
> 缠论口径、收盘价跌破（卖点涨破）即退场、5 个交易日有效期、一周前的展示日不显示未确认信号。
> 旧版 App（不带 `scope=all`）的前 10 在接口层由 `legacy_view` 按旧综合分现截，**不要**把截取或排雷写回快照。
> 次级别只补算最新一天「当天新出现的信号 + 旧版前 N 候选池」，封顶 `_SUB_LEVEL_MAX`（`sub_level_targets`），不要对全部信号补算（打满行情源）。
> 改取舍规则须升 `_mode_ns`（当前 `quant_mark2:all1`）。
> 雷达形态过滤（`chan/shape_filters.py`，仅雷达、详情页不受影响）**当前暂停**（`service._SHAPE_FILTERS_ENABLED=False`，
> 代码与测试保留；实测它在 5 日窗口内几乎不剔信号。当时雷达变空的真正原因是 78bee01 的「未确认不上榜」，
> 已在 2544d31 回退：宽松口径最后一笔上的信号照常上榜、`confirmed=false`，一周前的展示日不显示，收盘价跌破才退场）。启用时：按信号**成立日**（`detected_time`，宽松口径=czsc 事件点亮日）查 czsc 形态状态，
> 同向假突破 / 窄幅震荡 / 低波动命中即不上榜。**不要**改回按笔终点日判定（分型极值K线天然偏向信号反面），
> 也**不要**加回收盘位置（bar_classify）、区间震荡（cxt_range_oscillation）——真实数据校准会让雷达几乎清空，
> 见 `docs/superpowers/specs/2026-09-27-radar-shape-filters-design.md`「校准后调整」。改规则须升缓存键 `_mode_ns` 的 shape 版本。

> 量化研究约束（`app/services/quant_research`，设计见 `docs/superpowers/specs/2026-09-30-quant-research-design.md`）：
> 口径贴近 Seeking Alpha 因子评级但**只给字母等级**，文案不出现买卖导向词与数据供应商名（`copy.FORBIDDEN`，
> golden / 文案测试守护）；只展示时间（行情日、财报期、预期更新日）。指标全部用报表原始值自己算、带算式输入。
> **FMP 套餐 300 次/分钟**：所有新代码的 FMP 调用经 `app/cache/fmp_budget.acquire`（Redis 分钟计数，跨进程），
> 夜间批量 `priority="batch"` ≤150/分钟、遇 429 整体熔断 2 分钟；一次性脚本也必须限速（曾因 8 并发打满配额
> 导致线上被限流）。一致预期快照 `quant_estimate_snapshots` **只补不覆盖**（point-in-time，EPS 修正与日后回测依赖），
> 自有快照不满 90 天时 EPS 修正用外部一致预期趋势过渡（`eps_trend.py`，同源内算变化率、**不写入快照表**、
> 与 FY1/FY2 预期差 >15% 视为财年没对齐不用），攒满后自动切回自有快照；营收修正无外部趋势，仍需攒满 90 天。
> 2026-09-30 首份快照来自 `data/quant_seed/`（git 忽略），用 `scripts/quant_seed_import.py` 导入。
> **护城河**（`app/services/quant_research/moat/`，只展示、不计入综合等级，读取时附到响应 `moat` 字段）：参照 Morningstar，
> 宽 / 窄 / 无 + 趋势。证据 = FMP 10 年 ROIC（金融股 ROE）vs CAPM 资金成本；来源 = 大模型读最新 10-K Item 1 判断五种来源，
> **引用必须逐字核对**、3 次判断取中位数（MiniMax 温度 0 也不确定）。两者同时成立才有护城河。按 (股票, 10-K 编号, `moat.METHOD_VERSION`)
> 存 `quant_moat_assessments`，一份年报只评一次；部署后冷启动补齐、每天 UTC 12:00 查新年报（短锁 + 心跳，重启后可续跑）。
> **大模型额度**：与 App 对话 / 翻译共用 MiniMax 套餐，冷启动 24 路并发曾把套餐用量打满（2056）。现为 4 路 + 遇 429 全局冷却 +
> 每日新评估上限 `QUANT_MOAT_DAILY_LIMIT`（Redis 按 UTC 日计数，重启不清零）+ 用量到顶立即收工；紧急停用设 `QUANT_MOAT_ENABLED=false`。
> 判禁用词时保护公司名（Best Buy）。> 校准脚本 `scripts/moat_calibration.py`（12 只公开评级对照 11/12）。改判定规则须升 `moat.METHOD_VERSION`（会全量重评、耗大模型额度）。
> **冷启动**：已存结果的 `METHODOLOGY_VERSION` 与代码不一致时，启动自举立即重跑全量（锁键带版本号），改规则后部署即生效、不等夜间批量。
> **可解释**：App 上每个等级 / 分数 / 术语都可点开看「这一处」的解释（`Views/Quant/QuantExplain.swift`，带本股真实数字，
> 不做统一说明页）；指标大白话与算式输入项解释在 `glossary.py`。iOS 的分档 / 防抖 / 封顶常量由 `test_education.py` 对齐后端守护。
> 金融股的营收预期增速、市现率、FCF 利润率标「不适用」，且不做现金流阶段标注（口径不可比）。改分档 / 规则须升
> `METHODOLOGY_VERSION` 并重生成 golden（`UPDATE_GOLDEN=1 uv run pytest tests/services/quant_research`）。

> 新增一个投研模块时，通常需同步落地五处：`app/api/v1/<mod>.py`、`app/services/<mod>/`、`app/schemas/<mod>.py`、前端 `app/<mod>/page.tsx` + `lib/api/<mod>.ts`，并在 `api.py`、`TopNav.tsx` 注册。

## 缠论模块设计约束（app/services/chan）

改动 chan 前务必理解以下已确立的约束，否则容易走回头路。改动后跑 `uv run pytest tests/services/chan/`。
设计与演进记录见 `docs/superpowers/specs/2026-09-23-czsc-chan-refactor-design.md`。

**czsc 接入方式与性能（2026-10 实测，czsc 1.0.1）**
- czsc 1.0.1 的信号函数是 Rust 内核注册表，**Python 自定义信号函数不会被调用**（`CzscSignals` 配置里写 `模块.函数` 被静默忽略，实测调用 0 次）。
  所以「按 czsc 架构」= czsc 内核给结构 + 原生信号事件作触发，项目侧（`signals.py` / `leg_metric.py`）做组装与判定，不要尝试把背驰写成 czsc 信号函数。
- `cs.kas[label]` 与 `.bi_list` 每次访问都是**整份结构的副本**（耗时随 K 线数 / 笔数线性增长，实测 56→259 微秒），逐根循环里重复取是 O(n²)。
  `scan_bs_events` 每根 K 线最多取一次、没有触发 / 不记笔时刻就不取（51 只日线 43s → 22.5s，输出逐字节一致）。**不要**在逐根循环里再加 `cs.kas` / `bi_list` 访问。
  **自有 Rust 信号**（`rust/czsc`，czsc 1.0.1 的 vendoring 分叉，Apache-2.0；只在 `crates/czsc-signals` 新增 `dp.rs` 并在 `lib.rs` 注册 4 行，`czsc-core` 一行未改）：
  `dp_bi_track_V261001` 直接在内核里报告末笔终点 / 起点，Python 不再取副本（51 只日线 43s → 4.3s，输出与基线逐字节一致）。
  `czsc_signals._HAS_DP` 探测到分叉版就走 Rust 信号，标准 PyPI 版自动退回读 `bi_list` 的旧路径（两条路径输出一致，测试都过）。
  编译：`cd rust/czsc && uvx maturin build --release -i python3.13`（约 10 分钟，产物 `target/wheels`）；部署用哪个 czsc 见下方待定项。
  后续计划的信号（趋势前提 / b·c 段原始力度 / 一二三类触发）均按此方式加在 `dp.rs`，Rust 只输出原始量、判定与强弱分档仍在 Python（保持度量可切换、API 统一）。

**买卖点口径（`signal_policy.py`，统一接口 + 多套实现）**
- 「什么算买卖点」有多套口径，都实现 `SignalPolicy`（`czsc_families` / `assemble` /
  `split_unconfirmed` + 名称、版本、中英文案），在 `SIGNAL_POLICIES` 注册，按名字 `get_policy(mode)` 取。
  analyzer、`/chan/analysis`、`/chan/sub-level`、信号雷达（快照 / 自选 / 示例日）都只传 `mode`、走接口，
  **不要**写 `if mode == ...` 分支。**App 不提供口径选择、固定严格口径**（2026-10-01 起，iOS `SignalMode.current()` 恒为 strict；线上旧版 App 仍请求 loose）；
  `GET /chan/signal-modes` 仅为旧版 App 兼容与以后重新开放保留。
- `loose`（宽松，**默认**）= 严格化之前的口径：czsc 原生一/二/三类，最后一笔上的也输出（标未确认）。
  三族信号独立扫描、互不知晓，组装时（`generate_loose_signals`）必须做两条一致性约束（loose2 起）：
  同一笔终点命中多族只留一个（一类 > 三类 > 二类，`_DUP_PRIORITY`）；二类要求存在更早的同类一类，
  无源二类丢弃。**不要**去掉——否则会出现同日同价「一买+二买」（CTAS 2026-09-24）、约四成二类无源。
  `strict`（严格）= 下文「买卖点组装」的缠论原文定义。
- 新增口径（如「中等」）：写实现类 + 注册即可；雷达与次级别缓存键按 `policy.version` 自动隔离，
  定时预热 / 盘中次级别刷新跑**默认（宽松，旧版 App）+ 严格（新版 App）**两套（`scheduler._modes`），其余口径有请求时按需现算；
  旧版用户少了以后可以只留严格口径。
  **改了某口径的判定逻辑必须升它的 version**。

**引擎分工（2026-09 起接入开源库 czsc，Rust 内核，PyPI `czsc`）**
- 分型 / 笔 / 笔级中枢：czsc 计算，经 `czsc_adapter.extract_structures` 转回项目
  dataclass（`Fractal/Stroke/Pivot/MergedCandle`，schema 与前端不变）。czsc 会丢弃首笔
  确认前的前导K线（`merged_candles` 可能不从 raw_start=0 开始）；分型只取笔端点。
  **不要**用 `CZSC.bars_ubi` 当完整去包含序列（只剩未完成笔区域），用「各笔 bi.bars ∪ bars_ubi」重建。
- 线段 / 线段级背驰：**仍自研**（czsc 没有线段对象），输入为 czsc 转换后的笔。**不再算线段级中枢**
  （两年日线只有几条线段，线段级中枢常一个铺满全图；更高级别按 czsc 思路到周线看），
  `segment_pivots` 恒为空仅为接口兼容；走势类型只按笔级中枢判定。
  线段不变量：≥3 笔、方向由首笔定、连续子序列、**不吞没自身起点**、**终点是段内极值**、
  **首尾相接**（前段终点即下段起点，相接的必然交替）；已实现完整特征序列（第一种 + 第二种
  情况缺口前瞻确认；分型第一、第二元素间不做包含处理）。**不要**用「纯特征序列第一种情况」重写。
  线段被破坏（回调收复起点）时终点取段内极值笔；极值只在首笔（「一笔 + 横盘」，持平/浮点
  尾差不算新高）不成段；新段不成立而前段创新极值则延续前段；前段刚成形即被一笔创反向新极值
  （失败的反转）则撤掉前段、延续更早的同向段。未终结线段（数据到头）终点取当前极值、
  `terminated=False` 且不算确认，其后尾部不另起同向段。仅当一根大笔反转整条前段
  （任何划分都会吞没起点）才如实留一笔空档，空档后按实际走势定方向。不要为连续而硬连。
- **严格口径（strict）**的买卖点按缠论原文定义（宽松口径见上文「买卖点口径」，有意使用 czsc 原生
  二 / 三类，由 loose2 两条一致性约束兜底；下列「不要再用」只针对严格口径）：
  - 一类 = 趋势背驰：czsc `cxt_first_buy/sell_V221126` 的力度背驰事件（`czsc_signals.scan_bs_events`
    逐根推进，不回看未来）+ 趋势前提 `signals._in_trend`——信号前两个**已形成**（前三笔走完，
    `_formed_at`）的中枢区间不重叠且依次下移（一卖为上移），信号价离开后一个中枢。**不要**改成
    「已结束」：背驰后价格回到最后中枢会把它延伸，结束时间晚于一买（DXCM 一买曾因此漏掉）。
    **盘整背驰不算一类**；下一次同向笔又创新低 / 新高的一类作废（`_holds`，背驰段还在延伸）。
  - 一类的背驰（std6 起）= 缠论原文的 **c 段（离开 B）对 b 段（A、B 之间）**比力度（`signals._trend_leg_divergence`），
    b / c 段按笔级中枢取（`_trend_legs`）：czsc 的相邻中枢首尾相接（A 结束 = B 开始），**A 的最后一笔就是离开笔，算 b 段开头**；**离开笔** = 与中枢区间有重叠、沿趋势方向、终点越过边界的最后一笔（`_exit_stroke`），b 段（对 A）、c 段（对 B）都从各自的离开笔起算、含离开笔。czsc 会把离开笔吸收进中枢，**不要**从「中枢最后一个元素的终点」起算（曾因此 c 段被砍短、背驰几乎必然成立，见 tests 回归用例）。另需信号价越过 b 段终点（创新极值）。不要改回「末笔对前一同向笔」。中枢没有笔明细、或该度量缺数据（没传 MACD）时退回 czsc 笔级判定。
  - **背驰度量可插拔**（std7，`chan/leg_metric.py`，`DivergenceMetric` 接口）：`macd_area`（默认，原文 MACD 红绿柱面积）/ `force`（价差·量能·时长）。
    切换只改配置 `CHAN_DIVERGENCE_METRIC`，版本号 `std8.<度量名>` 自动隔离雷达缓存。**API 字段永远同一套**：`price_ratio / volume_ratio / length_ratio`
    任何度量都填，`area_ratio` 仅 MACD 面积度量填；强弱分档由度量自带的 `classify(primary_ratio)` 给出，各度量阈值各自标定：`force` 沿用价差比 0.6 / 0.8；`macd_area` 取 0.15 / 0.40（51 只美股日线 2023-01~2026-09 共 73 个一类信号的面积比三分位 0.14 / 0.41；c 段含离开笔后重标定）。
    新增度量：实现 `compare(c, b)` + 注册进 `DIVERGENCE_METRICS`，不要在判定流程里写 `if metric == ...`。
  - 同一笔终点同时命中二类与三类只留一个（三类 > 二类，与宽松口径同）。
  - 二类 = 一类后的第一次回落 / 反弹不破一类极值（`_derive_type2`，一类所在笔 i 的 i+2 笔）。
  - 三类 = 离开中枢后的第一次回落 / 反弹没有回到中枢（`_derive_type3`，复用 `pivot_phase` 的
    `_is_breakout` / `_classify_retrace` 配对，与「确认三买」同源）。
  - 严格口径**不要**用 czsc 的 `cxt_second_bs_V240524`（按端点价格重叠、不要求先有一类）或
    `cxt_third_bs_V230318`（5 笔局部中枢 + SMA34 均线过滤）——都偏离原文；实测 8 只股票一年
    由 62 个降到 9 个，全部符合标准定义。也**不要**换成 `tas_macd_first_bs_*` 这类纯 MACD 信号。
- 背驰度量：**力度口径**（`divergence.py`，与 czsc 一类买卖点同一口径，保证可解释）——价格创新
  高/新低，价差力度弱于前一个同向段，且量能或时长至少一项也更弱。力度三项取自 czsc 的笔
  （`Stroke.power_price/power_volume/length`），线段为所含笔汇总。强弱按价差比分档：<0.6 强、
  <0.8 中、其余弱（取自 169 个真实一类信号的三分位点）。**MACD 不参与任何判定**，仅为 API
  `macd` 字段（旧版 App 副图）保留计算；新版 App 图表下方为力度面板。

**数据层（根治性，别在算法层补数据的锅）**
- **前复权**：`skills/kline.py` 全链路用前复权价（FMP dividend-adjusted 端点、Yahoo
  `adjclose` 按比例回调 OHL、东财 qfq）。缠论是纯价格几何，不复权/半复权会在除息、
  A 股送转日产生人为跳空 → 假分型/假笔/假缺口。缓存键带 `qfq` 命名空间。
- **窗口锚定**：`ChanAnalyzer.analyze(visible_from=...)` 在用户所选起点前多取 warmup
  （API 层日线 180 天 / 周线 540 天）在完整序列上计算，再裁剪回可见窗口。裁剪时
  **笔与笔级背驰、线段与线段级背驰按下标平行，必须一并过滤**（下游 zip 依赖对齐）。
  详情页**始终预热**（`warmup_days` 参数已废弃被忽略）：czsc 要积累若干笔（一买>=5、三买>=7、
  二买>=15）才出信号，不预热图表开头会没有买卖点。信号雷达取数起点同步前移（`_fetch_start`），
  保证「从雷达点进详情」两边 K 线区间完全一致，有测试 `test_chan_window_alignment` 守护。
  30 分钟级别（`freq=30min`）可见区间收窄到最近 30 天、预热 20 天（Yahoo 分钟线上限约 60 天）。

**买卖点组装（严格口径 signals.generate_all_signals，信号质量别走偏）**
- 宽松口径（`generate_loose_signals`，线上旧版 App 使用）的对应行为：最后一笔上的信号**留在 `signals`、
  标 `confirmed=false`**（不产出候选，`candidate_signals` 恒空，雷达 `candidates` 也恒空）；
  `detected_time` = czsc 事件亮起的那根K线，不推后到下一笔走完。下面「只落在已完成的笔上」
  「成立日 = 下一笔首次成笔」两条**仅严格口径**。
- czsc 一类信号是持续多根K线的「状态」，在切换为买卖点时记一次事件，绑定当时最后一笔；
  按（类型, 笔终点）去重。二 / 三类的检测时间取所属笔完成的那根K线（扫描时逐根记录
  `stroke_done_at`，不回看未来）。
- **失效过滤**：所属笔若后续被延伸（端点不在最终结构中）即为失效信号，丢弃；买点只落
  下降笔终点、卖点只落上升笔终点。信号 time/price = 所属笔终点。
- **只落在已完成的笔上**（仅严格口径；`policy.split_unconfirmed` 在 `_mark_confirmations` 之后拆分）：最后一笔还在走，端点
  可能延伸甚至回到中枢，其上的买卖点尚不成立，不作为买卖点输出，而是放进
  `ChanAnalysisResult.candidate_signals`。雷达最新一天用它们补足剩余名额（`RadarDayOut.candidates`，
  `pick_candidates`），App 雷达只在上方显示「待确认」个数、不画气泡，详情页图上画成灰色虚线徽标，都不计入买点 / 卖点数——**不要**把候选
  混回 `signals`，也不要让它们占真实买卖点的名额。
- **成立日 = 下一笔首次成笔**（仅严格口径，std5 起）：`detected_time` 取从所在笔终点出发的下一笔**第一次成笔**的那根K线
  （`stroke_started_at`，czsc 逐根推进记录；缠论里一笔由后一笔确认），不早于事件亮起日。**不要**改回「下一笔整段走完」
  （`stroke_done_at` 下一笔最终版本，std4）：下一笔一路延伸时成立日跟着往后推，实测中位滞后 10 个交易日、P75 19 天，
  改后中位 6 天、P75 8 天。也不要用更早的「亮起日」：历史雷达日会提前看到未来才成立的信号。
- **展示日期两边一致**：雷达气泡日期 = `detected_time`；详情接口 `SignalOut.detected_time` 同值（日线纯日期、
  分钟线带时分），App 列表 / 结论卡 / 次级别列表显示它，图上标记仍画在 `time`（所属笔终点，极值K线，
  通常在出现日左侧几根）。守护测试 `tests/services/chan/test_signal_out.py`。
- 强度：一类按 czsc 同一判据复算的力度比分档（基准 = max(前一个同向笔, 关键笔均值)，
  见 `signals._first_bs_force`），说明写出价差/量能/时长三项比值；
  二/三类 = 信号前**最近已结束**中枢的级别 + 余量（`_type23_strength`），尚未结束的中枢不参与。
- 用语统一（`pivot_phase.py` 与 App 流程图同一套）：状态 = 中枢形成 / 中枢震荡 / 离开中枢 /
  确认买卖点 / 背驰 / 转折；动作 = 形成中枢 / 突破 / 回落（向上离开后）/ 反弹（向下离开后）/
  回到中枢；ZG / ZD 对用户写「中枢上沿 / 下沿」。不用回踩、反抽、离开段、假突破（有测试守护）。
- 描述文案不出现 czsc 等第三方库名。
- `pivot_phase.py`（中枢阶段徽标）仍用自研结构判定阶段；只有回抽笔终点上有**同类**
  买卖点信号时才写「确认X买/卖」，否则只描述结构（如「回落未跌回中枢」），保证徽标
  与图上买卖点一致。`replay.truncate_as_of` 须同步按时点截断 signals。
- **次级别确认**（`sub_level.py` 纯函数 + `sub_level_service.py` 编排，接口 `GET /chan/sub-level`）：
  级别逐级递推不跨级（`LEVEL_PAIRS`，`parent_freq` 参数）：日线 × 30 分钟最近 2 个交易日、
  周线 × 日线最近两周。大级别 `recommendation.bias` 定方向 × 次级别买卖点 → 共振/逆势/等待/不可用；
  **唯一入口 `current_sub_level`**：雷达气泡与详情页共用（固定口径：大级别窗口不随详情页日期范围变、
  截止日取服务器当天、代码归一化；按结论缓存 1h，雷达盘中每 30 分钟 refresh 覆盖），不要再各算各的。
  注意详情页请求带 `max_age=LIVE_MAX_AGE`（60 秒），盘中会比雷达气泡上的共振标记更新，两者最多差一个
  30 分钟刷新周期；收盘后数据定型即一致。
  30 分钟失败只降级为 unavailable，不影响日线。30 分钟数据：美股 FMP 分段拉取，港股/A 股
  Yahoo `30m`（上限约 60 天）。分钟线时间为交易所本地 `YYYY-MM-DD HH:MM`（`ts_date` 零点才输出纯日期）。
  信号雷达只对最新交易日的部分信号补算（`attach_sub_levels(only=sub_level_targets(...))`）。
- 走势类型 `walk_type`（up_trend / down_trend / consolidation / none）由中枢排布判定，
  经响应字段暴露给前端。
- 形态分析（recommendation）是**多因子加权净值**，单条依据可与结论方向相反是设计使然
  （避免因单信号来回翻脸），改权重看 `bias.py`。

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
