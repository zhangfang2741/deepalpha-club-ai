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
| 宏观 / 行业 | `/macro` | iOS 雷达页顶部：市场分段条与「大盘环境」条合成一张市场卡；其下是行业横条（「全部行业」+ 各行业胶囊，从强到弱，点选即筛雷达 `SignalRadarViewModel.sectorFilter`，末尾列表按钮打开行业强弱面板 `SectorBoardSheet`）；自选页顶部环境横幅；自选页顶部环境横幅 | 大盘状态(regime) + 5 个驱动因素 + 未来 7 天宏观日历；行业相对强弱（`?date=` 按雷达所选日）。`/signal-radar/sector-pools`、`/sector-day` 仅为旧版 App 保留（新版 App 用气泡自带的 `sector` 在本地按行业筛选）。大盘状态与行业强弱美股 / A 股 / 港股都有（A 股 / 港股无驱动因素与日历；行业为申万 / 恒生一级） |
| 行业恐慌 | `/industry-panic` | `/industry-panic` | 各 GICS 行业 ETF 的 RSI 情绪 + 估值 + 板块状态(行业级 regime) |
| ETF 资金流 | `/etf` | `/etf` | 资金流热力图 + 偏离度 |
| 行业估值 | `/valuation` | （并入行业恐慌页） | GICS 行业 PE z-score |
| 缠论 | `/chan` | `/chan` | 缠论分笔/中枢/背驰 |
| 信号雷达 | `/signal-radar` | iOS「雷达」Tab（页面标题「市场雷达」） | 扫描各市场指数成分股跑缠论，**只陈列事实**：某天在场的全部买卖点按出现时间排（`scope=all`，新版 App；不带 scope 的旧版 App 在接口层按旧综合分截前 10）。App 用严格口径，只画已成立的买卖点（「待确认」只在雷达上方显示个数）。气泡：红买绿卖、深浅=信号强弱、大小=一二三类（直径 58 / 72 / 86，再乘时间系数 1.0→0.7，最小 44；允许叠 30%，拥挤缩放上限 0.7、缩放下限 0.85——信号多时折叠而不是继续缩小，标普与纳指同类气泡大小一致；稀疏日放大：气泡总面积不到画布 20% 时最多放大 1.3 倍，一二三类比例不变）；指数切换并进顶部市场分段条（已选中的市场下面显示当前指数名，点它弹出该市场的指数列表；自选仍在这个列表里），雷达画布里只有左下角一个「名单」按钮（overlay，不占版面）、不预留禁区；摆位只取决于数据与画布大小（以前实测切换器大小当禁区，量出来后气泡会重摆、跳一下），气泡漂浮动画起点就是 -6pt，会员状态用上次结果当初值（避免先按未订阅摆示例日再切）；同心环模式下信号数 ≤ 10 个必须全部画出来（先放宽时间圈带、再缩小气泡），超过 10 个才折叠到「另有 N 个 · 查看全部」；由内向外越靠中心越新、互不重叠（`SectorRadarLayout.pack` 整圆一个扇区）。按行业分扇区的画法已关闭（`SignalRadarView.sectorFieldEnabled=false`，代码与测试保留）。非会员的免费示例日（上个月 1 号）永远排日期轨第一格并默认选中：它恰好在后端 30 天真实窗口里时（每月前几周）把真实那一天挪到最前面而不是留在第 20 来位（日期轨只摆前 10 格，否则示例日不在轨上、整条轨不高亮）。顶部三格 / 扇区标签点开是底部面板（环境 / 行业 / 当日信号列表）；点气泡、或列表里的某一行都直接进缠论详情页（2026-10-05 起删除了中间的「大盘 / 行业 / 结构 / 基本面」四层事实页） |
| 威科夫 | `/wyckoff` | `/wyckoff` | Wyckoff 阶段/事件 |
| 一目均衡表 | `/ichimoku` | `/ichimoku` | Ichimoku 云图信号 |
| 分析师上调 | `/analyst-upgrades` | `/analyst-upgrades` | 目标价上调榜（SP500/Nasdaq100）；`/overview/{symbol}?market=us\|cn\|hk` 为缠论 App 详情页「分析师评级」分段（A 股 / 港股五档为买入 / 增持 / 中性 / 减持 / 卖出，只对带 `bucket_labels=1` 的新版 App 返回） |
| 基本面研究（代码内仍叫 quant_research） | `/quant-research` | 缠论 App 详情页「基本面研究」分段 | 五维度（估值/成长/盈利能力/动量/EPS 修正）GICS 板块内百分位 → A+~F，三层下钻 + 方法说明；样本：美股标普1500、A 股市值前 1800、港股港股通 ∪ 市值 ≥ 20 亿港元 |
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
> **行业严格按 GICS 11 个一级行业**（2026-10-01 起半导体并回科技，不再单列；App 只做一级、不下钻细分，宏观接口 `has_children` 恒 false）。改行业划分须升雷达 `_mode_ns`（当前 all4；A 股 / 港股改申万 / 恒生时漏升过，导致旧快照行业 key 对不上面板），旧标签随快照失效。
> 行业池（每行业按旧综合分的前 N）只给旧版 App 的行业筛选用。
> **A 股 / 港股行业标签**（2026-10-05 起，`sectors.load_sector_tags`）：A 股用本土**申万一级 31 个**（key 即中文名，如「电子」，不套 GICS；
> 东财行业名即申万二级，`cnhk/sectors.CN_INDUSTRY_TO_SW` 归一级，与 `CN_INDUSTRY_TO_GICS` 键集一致有测试守护，新行业两张表都要补）；
> 港股同理用本土**恒生行业分类一级 12 个**（key 即中文名，如「资讯科技业」，`HK_INDUSTRY_TO_HS` 与 GICS 表键集一致有测试守护，不套 GICS、不用 `HK_OVERRIDES`）。整市场一次取、Redis 缓存 24 小时，取回过少视为残缺不缓存。
> **A 股 / 港股大盘状态**（2026-10-05 起，`regime/cnhk.py`，表 `regime_market_features`，带 market 列，不动美股表）：与美股**同一条管线**
> （`features.build_feature_series` → `engine.run_walk_forward` 走-前向 HMM，月末冻结、滤波后验、不回改），只换取数：基准 A 股沪深 300 ETF / 港股盈富基金，
> 进攻 / 防御 / 现金三个等权 ETF 篮子见 `MARKET_CONFIGS`（Yahoo 日线，`skills.kline._fetch_yahoo`）。两个市场没有可用的波动率指数，特征里的 `vix` 槽换成
> 「20 日 / 60 日已实现波动比」。选篮子要避开 Yahoo 历史残缺的品种（2828.HK 只有约 600 根，会把整个市场的共同历史截短），现金篮子年化波动须在 2% 内。
> 调度 `regime/scheduler.run_cnhk_regime_scheduler`：A 股 UTC 07:40、港股 08:40 工作日，启动补跑，子进程降优先级（单市场约 1 分钟），紧急停用 `REGIME_CNHK_ENABLED=false`。
> 已知局限：模型把高波动当偏避险（与美股同口径），A 股 2024-10-08 国庆后涨停潮被判成避险；两市场 ETF 上市较晚，有状态的区间约从 2022 年起。
> **A 股 / 港股行业状态**（`regime/cnhk_sector.py`，表 `regime_market_sector_features`）：行业指数 = 该行业**市值最大的 8 只成分股等权合成**
> （成分股与行业归属就是雷达打标签用的东财数据；**不用行业 ETF**——申万 31 个行业里不少没有干净 ETF、Yahoo 上沪市 ETF 名称也核对不了，
> 凭记忆猜代码会猜错，如 159715 是稀土不是纺织服饰），再喂给美股同一套行业管线 `sector_pipeline.compute_sector_regimes`（每行业独立走-前向 HMM，特征含相对大盘强弱 RS）。
> 成分股少于 3 只的行业不出强弱。每行业约 15 秒（回看 1500 天；5 年约 50 秒），A 股 31 个约 8 分钟、港股 12 个约 3 分钟，所以**独立一轮**
> （`run_cnhk_sector_once`，单独的锁与子进程，大盘状态不等它）；每个交易日约 250 + 100 次 Yahoo 请求（并发 3 + 间隔）。
> 行业 key 是中文名；英文名在 `cnhk/sectors.NATIVE_SECTOR_EN`（接口按 `lang=en` 返回，App 本地兜底走 `L(key)` + en 文案；有测试守护 43 个行业都有英文名，新增行业须补）。
> `/macro/{cn|hk}/sectors`（`macro.service._native_sector_board`）返回本土行业全集 + 强弱（没算出来的行业强弱为空，App 不画强弱条、不写「最强」）+ 雷达当日买卖点数。

> **产品目标：让普通人看得懂、能学到知识、靠理解而不是盲目去做投资决策**（2026-10-06）：任何新界面 / 文案先问「一个没学过金融的人能看懂吗」——术语第一次出现要有大白话解释或能点开看词条（`lessons.json` / `AnalysisTermLink`），数字要告诉人「意味着什么、不意味着什么」，结论要能追到推导（见下条）。
> 边界：帮人理解 ≠ 替人决策。仍然只陈列事实与知识，不出现买卖导向措辞、不承诺收益（App Store 3.1.1 / 5.2.5 的高风险措辞，见 `ios/AppStore/chan/store-listing.md` 说明），免责声明照常保留。

> **学习内容**（面向普通人，2026-10-06）：`Resources/{zh-Hans,en}.lproj/` 下三份 JSON——`glossary.json`（名词小词典，稳定中文键 `key`，含大白话 / 举例 / 不代表什么）、`guide.json`（新手入门 7 篇）、`lessons.json`（缠论入门 9 篇）；
> 名词在界面上用 `TermChip` / `TermHint` / `GlossaryLink(term:)` 点开（先查缠论教程索引 `GlossaryIndex`，再查词典），推导弹层（`DerivationResult`）带「这说明 / 这不说明 / 相关名词」。
> 新手导览 `OnboardingTourView`（首次进雷达弹一次，学习页可重看；「我的」页的「重看新手导览」2026-10-09 起已去掉）；专业数值（面积比 / 价差比 / 时长比）默认折叠，「我的 → 显示专业数值」打开（`ProDetails.key`）。
> **体验约束**（体验不好没人用）：说明类内容一律**渐进披露**——第一屏只给结论和「这说明 / 这不说明」，推导过程折叠、点开才展开；**不自动弹全屏**打断人（新手导览改为首次进雷达时展开一次悬浮的流程图、里面有入口，不弹 sheet）；入口字再小也要给足点击热区（≥ 44pt 或加 padding）；新增界面元素先问「会不会让主屏更挤、更慢」。
> **新增术语要同时补词典条目（中英）**；推导里 `terms:` 引用的键必须能查到（`tests/ios_content` 守护）。解释一律不写成买卖建议。

> **产品介绍放在学习页「新手入门」**（2026-10-06）：`guide-app-tour`（五个 Tab 各做什么）、`guide-app-radar`（雷达页怎么读）、`guide-app-detail`（个股分析页怎么读：结论卡 / 图 / 三视角 / 买卖点 / 次级别 / 自选 / 分享 / 免费与会员）、`guide-relation`（市场 / 行业 / 基本面 与缠论结构的关系）。
> 「怎么算的」仍**散落在各页面数字旁**（用户明确要这样，不要收拢到学习页）。改页面功能 / 入口时，对应的产品介绍篇（中英）要一起改。App 默认打开「分析」Tab。

> **最新财报**（2026-10-06，基本面研究页顶部「最新财报」卡 + `GET /quant-research/{market}/{symbol}/report`，`quant_research/report.py`）：美股取 SEC 最近一份 10-K / 10-Q（外国公司 20-F / 40-F，网页文档）、A 股 / 港股取东财公告里最新的定期报告 PDF（A 股只收「…报告全文」栏目；港股收 年報 / 中期報告 / 季度與中期業績公告）。
> 后端只给链接和元信息（Redis 12 小时），文件由 App 自己下载到本机缓存（`ReportCache`，Caches/reports）、App 内阅读（PDF 用 PDFKit、SEC 网页用 WKWebView），阅读页左上角分享面板可存到「文件」。SEC 请求必须带声明身份的 User-Agent（`tenk.SEC_HEADERS` / App 的 `ReportCache`）。
> **最新年报**：同一个接口加 `?kind=annual`（美股 10-K / 20-F / 40-F、A 股「年度报告全文」、港股「年報」；年报埋得深，公告多翻到 6 页）；基本面研究页的卡片里「最新财报」下面多一行「最新年报」，和最新财报是同一份时不重复列。
> **AI 总结入口在阅读页右下角**（`ReportReaderView` 的浮动按钮，只有财报阅读页带 `ReportSummaryContext`）：打开阅读页时用 `?peek=true` 静悄悄探缓存（不触发生成），有缓存按钮高亮、点开直接显示；没有才触发生成并轮询。`?kind=latest|annual` 决定总结哪一份。
> **财报中文要点**（`GET /quant-research/{market}/{symbol}/report/summary`，`quant_research/report_text.py`（挑章节）+ `report_summary.py`（大模型 + 缓存），App 的 `ReportSummarySheet`）：
> 美股取 MD&A + 利润表、A 股 / 港股 PDF 取「财务概要 + 管理层讨论与分析」（目录页跳过、找不到章节退回开头），喂大模型结构化输出（headline / 关键数字 / 要点 / 风险 / 管理层表述），只依据原文、不预测、不给买卖建议（`_BANNED` 措辞命中的条目直接丢）。
> **同一份财报只生成一次、全员共用**（Redis 60 天，键按财报链接哈希）；大模型额度与 App 对话 / 翻译共用，所以有：每日新生成上限 `REPORT_SUMMARY_DAILY_LIMIT`（UTC 日计数）、同一份财报的生成锁、失败冷却（10 分钟 / 额度用尽 30 分钟 / 文字不可读 24 小时）、紧急停用 `REPORT_SUMMARY_ENABLED=false`。生成放后台，接口立刻返回 generating，App 每 3 秒轮询。
> **港股 PDF 乱码的兜底**：报告 PDF 提不出文字时，`report.find_results_announcement` 找同期的业绩公告（年报 → 末期 / 全年業績、中期报告 → 中期業績、季度 → 季度業績，披露日在报告前 150 天内）改用它做总结（阿里年报乱码、同期业绩公告可读，已实测）；腾讯的各期文件全是乱码，仍然只能提示「提取不出来」。
> PDF 提取用 pypdf（`uv.lock` 是手工补的，因为沙箱里 `uv add` 解析不动 tradingagents；以后在本机 `uv lock` 会规范化）。**部分 PDF 字体没有字符映射、提取出来是乱码（实测腾讯港股中期报告）**：`looks_readable` 判断后明确告诉用户「文字无法提取」，不硬编。
> 同一套阅读器也用于分析师评级里的研报原文（A 股 PDF）/ 相关报道（美股、港股，网页）。

> **量化指标一律要有「怎么算的」推导**（2026-10-06 产品原则）：App 上任何算出来的结论（状态、分数、等级、强弱、门槛、角标、买卖点类型）都必须能点开看到「结论 → 几步推导（带这一处、这一天的真实数字）→ 局限」。
> 统一外壳 `Views/Components/Derivation.swift`（`DerivationContent` / `DerivationLink`，底层复用量化研究的 `.quantExplain` 弹层）；每项文字单独写、不做统一说明页：
> 宏观四项 `Views/SignalRadar/MacroDerivations.swift`（市场状态用后端 `state.inputs` 的当天原料、驱动因素用 `flat_band`）、雷达 `RadarDerivations.swift`（基本面门槛带 `quality_share / min_count / floor`）、买卖点 `Views/Analysis/SignalDerivation.swift`（严格口径）；基本面研究早已有（`QuantExplain.swift`）。
> **改算法 / 阈值 / 权重时，对应的推导文字（中英）必须一起改**（口径来源已写在各文件头注释里）；新增量化指标没有推导说明不算完成。
> 情绪分是第三方公开指数、我们只展示（说明里照实写「不是我们自己算的」，不出现供应商名）。

> **用户界面里「好股票」一律叫「基本面」**（2026-10-06：流程图第三步「基本面」、名单「基本面名单」、算法说明「什么是基本面筛选」；代码、接口、测试里仍叫 good / quality，不改）。

> **雷达 = 好股票的缠论买卖点**（2026-10-06 起，门槛由我们定、**不让用户选**）：用户要感知的是「市场怎么样、行业怎么样、好的股票有哪些、有没有买卖点」——顶部市场卡 / 行业横条 / 雷达画布 / 好股票名单依次回答。
> 此前试过的「基本面研究」并列 tab（每日综合评级升降、综合等级榜、分析师评级 tab）都已下线：A 股 / 港股评级历史太短长期空白、榜单几乎不变、全红榜单读起来像推荐。**不要**再做并列 tab / 日期轨式的基本面视图。
> **基本面门槛**（`signal_radar/quality_view.py`）：新版 App 请求带 `quality=good`（仅 `scope=all` 生效），接口层**现算、不写回快照**（快照仍存全部在场信号；旧版 App 不带 quality，行为不变）；
> 只留**当前**综合等级达标的股票的买卖点——用当前等级、不是信号当天的（评级历史短，历史日期同样只留当前达标的）；**门槛随股票池自适应**（`quality_view.choose_cutoff`）：目标 = 有评级股票的前 `GOOD_SHARE`（25%），至少 `GOOD_MIN_COUNT`（8）只；从高到低累计各等级只数，到达目标的那一档即门槛、**整档纳入不在档内切**（界面才能写「X 及以上」），且不低于 `GOOD_FLOOR`（B，小池子 / 整体偏弱的池子不凑数）。2026-10-06 实测：纳指 100 → B（16 只）、标普 500 → B、沪深 300 → A-（78 只）、恒生指数 → A-、恒生科技 → B（8 只）；
> 留下的信号 `quant_grade / score / as_of` 换成当前等级（气泡最后一行写等级字母）；买卖点数 / 行业计数按留下的重算；响应带 `quality_threshold / quality_good_count / quality_rated_count`，App **不**在雷达页上方加说明行 / 四步条（市场和行业上面的卡片 / 横条已经有了）：标题「市场雷达」旁一个折叠钮（`flowTitle`），点开是一张**悬浮**的简单流程图（`flowPanel`，overlay 盖在页面上方、不占版面不挤压下面的内容，点外面收起；①市场 ②行业 只写「看下面…」，③好股票「N 只 · X 及以上」④结构「M 只 · 近期出现结构信号」（**不提买卖点**：它是投资观察流程、不引导操作，底部带一句「不构成投资建议」的免责），默认折叠，折叠时页面和没有它一样干净）；雷达画布左下角「名单」按钮（`goodListButton`，会员功能；2026-10-09 起免费用户选中示例日时也显示，名单里的买卖点只按示例日那一天判断，不透出锁住的日期；overlay 叠在画布角上、不参与气泡摆位）打开基本面名单（名单跟顶部行业筛选联动：选了行业只列该行业的股票，`GoodStocksSheet.sectorKey`）。
> **评级读取失败时原样返回（不能因为评级挂了让雷达变空）**；达标名单 / 评级排序 Redis 缓存 3 小时（`signal_radar:good:v1:*`、ranked），由定时任务每小时巡检刷新（`quality_view.warm_good`，缓存超过 1 小时才重算）——以前 10 分钟过期，每次过期后第一个用户要等读评级库（A 股 ~6 秒、标普 500 十几秒）。改门槛改 `GOOD_SHARE / GOOD_MIN_COUNT / GOOD_FLOOR`，无需升 `_mode_ns`（不进快照）。
> **分析师评级只作角标**（`RadarSignal.analystUp / analystDown` → `analystMark`，`RadarBubble` 右上角白色小胶囊）：近 90 天券商净上调「▲n」（红）/ 净下调「▼n」（绿），净 0 或没有数据不画；只做美股（A 股东财研报无上调 / 下调字段、港股只有最新评级）。
> 数据 = FMP 个股评级变动 `grades`（`signal_radar/analyst_events.py`），**只对留下信号的好股票拉**，**接口只读 Redis 缓存**（`signal_radar:analyst:v2:{symbol}`，24 小时 TTL、6 小时算过期）；缺失 / 过期的由后台任务补（`FmpClient` 批量额度、并发 4、带锁），响应 `analyst_pending` = 还在补的只数，App 的静默轮询（`refreshWhileBackfilling`，90 秒）在 >0 时继续重拉。**不要**在请求路径里同步逐只拉 FMP。
> **买点优先**（2026-10-06）：好股票里的买点是用户最关心的——画布超过 `ringFieldCap` 个要折叠时先折卖点（`SignalRadarView.buyFirst`，买点排前、各自保持时间从新到旧）；好股票名单分「近期有买点 / 近期只有卖点 / 暂无买卖点」三组，每行优先展示最近的买点。
> **好股票名单**（雷达上方「名单」入口，`GoodStocksSheet` + `GET /signal-radar/fundamental-top`，会员功能 + 免费用户的示例日）：当前综合等级达标的股票，分三组（有没有买卖点按雷达当前各展示日的信号判断），每行写等级、券商角标与最近一个买卖点；点行进个股详情。名单取全池前 50（按等级高 → 低、综合分高 → 低），门槛用雷达响应的 `qualityThreshold` 在 App 端截。
> 旧接口 `GET /signal-radar/grade-events`（每日升降）与 `/analyst-events`（每日券商净升降）后端保留、App 不再使用。

> **雷达默认指数**（2026-10-06 起，`universe.py` 的 `is_default`）：美股标普 500、A 股沪深 300、港股恒生指数（此前是科技指数）；iOS `SignalRadarViewModel.defaultUniverseKeys` 兜底与它一致。改默认须两边同步。

> **冷启动预热顺序**（`scheduler._prewarm_order`）：部署 / 口径换版本后缓存全空，主扫描按「默认指数先于其它指数 → 中等 > 严格 > 宽松 → 剩余 TTL 短的先」排；检查是否就绪用 `uv run python scripts/radar_cache_status.py`（逐个列出主快照 / 示例日 有 / 缺 / 陈旧）。
> **免费示例日预热**（`scheduler._prewarm_demos_all`）：免费用户唯一能点开的是示例日，所以启动后**先**预热默认指数的示例日（严格口径优先）、再跑主扫描，之后每小时巡检一次（`_demo_keepwarm_loop`：月初换目标日、Redis 被清、降级快照自愈）；缓存 3 天、12 小时算陈旧（先返回旧的再后台重算）。
> 信号雷达扫描约束（`app/services/signal_radar`）：同一 (口径, 市场, universe) 任一时刻只跑一轮全量扫描
> ——接口与定时预热共用 `scan_lock_key` 原子锁（`acquire_lock` = SET NX EX），主动刷新有 5 分钟冷却；
> 所有扫描 / 补算 / 示例日拉 K 线共用进程级闸门 `_fetch_gate`。拉数失败（限流 / 不可用）的成分股
> 由 `_backfill` 在后台逐轮慢慢补算、补上即重写快照（响应 `pending_symbols` = 仍在补算的只数），
> 轮次号存 Redis（`incr_with_ttl`），新一轮扫描开始旧补算自动退出。免费示例日（`compute_demo_day`）同一套补算。
> 补算进度记为 Redis 标记（`signal_radar:backfill:*`，含进程 owner），进程重启后 `scheduler._resume_orphan_backfills`
> 在启动预热之后接手别的进程没补完的。**不要**绕过锁直接起全量扫描。
> **雷达只呈现事实、不做推荐**（2026-10-01 起，设计见 `docs/superpowers/specs/2026-10-01-radar-facts-top-down-design.md`）：
> 快照存每天**在场的全部信号**、按出现时间从新到旧（`order_by_time`），不打分、不截前 N、不按共振重排；
> **基本面排雷已取消**（快照里评级只标注，`quant_filter.attach_grades` 不再剔除任何信号；新版 App 的「好股票」门槛是接口层 `quality=good` 另算，见上）。只保留定义层面的规则：
> 缠论口径、收盘价跌破（卖点涨破）即退场、5 个交易日有效期、一周前的展示日不显示未确认信号。
> 旧版 App（不带 `scope=all`）的前 10 在接口层由 `legacy_view` 按旧综合分现截，**不要**把截取或排雷写回快照。
> 次级别只补算最新一天「当天新出现的信号 + 旧版前 N 候选池」，封顶 `_SUB_LEVEL_MAX`（`sub_level_targets`），不要对全部信号补算（打满行情源）。
> 改取舍规则须升 `_mode_ns`（当前 `quant_mark2:all4:win2y_wu1y`）。
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
> **护城河**（`app/services/quant_research/moat/`，只展示、不计入综合等级，读取时附到响应 `moat` 字段；**iOS 暂时不展示**：`QuantMoatCard.isEnabled=false`，2026-10-05 起「以后再说」，后端评估、接口字段与卡片代码都保留，改回 true 即恢复）：参照 Morningstar，
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

> A 股 / 港股基本面与分析师评级（`app/services/quant_research/cnhk/` + `analyst_upgrade/overview_cnhk.py`，设计见 `docs/superpowers/specs/2026-10-03-quant-cn-hk-design.md`）：
> **评分管线与美股完全共用**（`batch.score_and_store` / `builder`），cnhk 只做「取数 + 换算成 FMP 同形输入」；市场差异集中在 `markets.MarketProfile`
> （样本叫法、没有数据源而不显示的指标、护城河仅美股），**不要**在评分流程里写 `if market == ...`。
> 数据源（均实测从 Railway 美国机房可达）：东财数据中心 F10 报表（A 股按报告期批量全市场，港股逐只）、东财 F10 盈利预测 / 研报列表（A 股预期与评级）、
> 经济通盈利预测页（港股预期 / 评级 / 目标价）、Yahoo 收盘价（`fetch_kline`）、FMP forex（港股汇率）。FMP 的 A 股 / 港股报表与评级套餐不含（402）；
> 东财行情 push2 海外断连；同花顺海外 301（线上从未写入过旧的 A 股快照，旧任务已删除）。所有东财 / 经济通请求走 `cnhk/http.py` 的进程级闸门（并发 + 间隔 + 重试、`trust_env=False`）。
> **港股报表金额一律是人民币**（东财已把美元 / 港元申报的折成人民币；报告清单 CURRENCY 是原始申报币种），统一折成港元再算；预期按经济通表头单位（分 / 港仙 / 美仙）换算，
> **快照存申报币种原值**（否则汇率波动会被当成 EPS 修正）。报表是累计口径，`reports.to_quarters` 换算单季（相邻累计点之差平摊，TTM / 同比 / 上一财年精确）。
> A 股利润表 G 表含全部公司（`ORG_TYPE` 定类型），现金流 / 资产负债表按 G/B/S/I 分表；金融类不算 EV / 毛利 / EBIT(DA) 类（标「不适用」）。
> A 股评级分布用 F10 官方「6 个月内」统计（研报列表只收录部分研报）；港股只有各券商最新评级、无历史。行业为东财行业静态映射到 GICS 11 个一级（`cnhk/sectors.py`，新行业须补映射）。
> 调度：A 股工作日 UTC 09:00、港股 UTC 10:00，冷启动自举同美股；紧急停用 `QUANT_CNHK_ENABLED=false`。A 股报表每 30 天全量一次，平时只刷新披露窗口内的期次。

> **综合分按公司阶段加权 + 财务稳健维度**（`METHODOLOGY_VERSION` q7，2026-10-09）：基本面研究现为**六个维度**（估值 / 成长 / 盈利能力 / 动量 / EPS 修正 / 财务稳健），综合分不再等权——
> 权重由 `stage.STAGE_WEIGHTS` 按公司阶段（初创 / 成长 / 成熟 / 调整 / 收缩）给定（成长期看增速、成熟期看估值与盈利、初创 / 调整 / 收缩期更看重财务稳健），无阶段（金融股等）等权；
> 只在可用维度间重新归一（EPS 修正积累中、金融股没有财务稳健时照常）。**改权重表须升 `METHODOLOGY_VERSION`**，并同步 `methodology.py`（直接读表，自动同步）与 iOS 推导文案；
> 每行和为 1、每阶段财务稳健权重 ≥ 一票否决门槛、成长 / 初创期估值权重 < 门槛、插值处处和为 1 且无断崖，都有 `test_stage.py` 守护。
> **一票否决只对综合分里权重 ≥ `CAP_MIN_WEIGHT`（15%）的基本面维度生效**（`scoring.overall`；动量 / EPS 修正在 `CAP_EXEMPT_DIMS` 里永远没有否决权——价格 / 预期类不是公司基本面，30 只科技股实测 AVGO 动量 F 恰在门槛上）：成长期估值贵不再一票封顶 C+；财务稳健在每个阶段都有否决权。iOS 的 `capMinWeightPct` 由 `test_education.py` 对齐。
> **权重连续插值**（`stage.blend_weights`，不再按阶段档位整行跳变，也不再需要滞回）：营收同比 × 经营现金流占营收两条轴，过渡区以原阶段门槛为中心各延伸 5 个点
> （同比 10%~20% / 0%~−10%、3 年复合 5%~15% 给高增长打折、现金流利润率 −5%~+5%），远离门槛时就是 `STAGE_WEIGHTS` 对应行；阶段（`classify_stage`）只作界面标签。
> 一票否决门槛仍是离散判断（插值权重刚好越过 15% 时估值 F 会被封顶），这是已知的剩余断点。
> **盈利能力指标有权重**（`MetricDef.weight`，维度分 = 百分位按权重加权平均，`scoring.weighted_percentile`）：EBIT / EBITDA / 净利率、ROE / ROA、资产周转率各 0.5（同为 GAAP 利润的变体，避免同一信息被重复计算六遍），
> 毛利率 / 自由现金流利润率 / 扣股权激励后自由现金流利润率（`fcf_sbc_m`）/ ROIC 为 1；现金口径合计约 29%。`test_metrics` 守护；方法说明里的权重清单直接读 `METRICS`。`fcf_sbc_m` 美股才有（FMP 现金流量表有股权激励），A 股 / 港股登记为无数据源，金融股不适用。
> **估值倍数按阶段取舍权重，比较对象不变**（`stage.VALUATION_WEIGHTS` + `blend_valuation_weights`，同一套增速 × 现金流连续插值）：估值维度 14 个倍数的**百分位仍和整个板块比**（不做「只和同阶段比」——要保证行业维度可比、板块样本也不够分层），
> 只改各倍数在估值分里的权重：成熟期 14 项按信息类别分权（盈利 3 / 企业价值·利润 3 / 营收 3 / 市净率 2 / 市现率 3，合计 14，类内再等分，q8；旧版等权会把同一类信息数 3~4 遍）；成长期看前瞻 / PEG / 营收倍数 / 市现率、不看市净率与 EV·EBIT TTM；初创期（烧钱）只看营收类倍数（利润类倍数会被当成最差）；调整期偏盈利与资产；收缩期不看前瞻与 PEG。
> 权重为 0 的倍数仍展示（`MetricOut.weight=0` + 状态说明），不进分数也不占「参与数」（`score_dimension(metric_weights=...)`）；`MetricOut.weight` 是这家公司实际生效的权重。改表须升 `METHODOLOGY_VERSION`，`test_stage.py` 守护（行覆盖 14 项、成熟期全 1、初创期利润类为 0、插值连续）。
> **百分位并列取平均位次**（`grading.percentile_of`）：净现金（净负债比 0）、不烧钱（年数封顶）、没有利息（倍数封顶）这类指标大量公司并列在极值（实测 31% / 43% / 97%），
> 以前并列者全拿 100 分位——界面写「高于板块 100% 的公司」不真，稳健维度也被整体抬高（样本均分 63 → 49）。无并列时结果与旧算法完全一致（`test_grading` 守护）。
> **综合分在同阶段公司里排位**（q8，`scoring.build_cohort_distributions` / `finalize_overall(cohort_dists)`）：权重按阶段调整后成长股综合分系统性偏高（q7 实测美股成长期 B- 及以上 61%、成熟期 35%），所以综合分的百分位改为和**同阶段标签**的公司比（`COHORT_MIN`=30、仅 `COHORT_STAGES` = 成长 / 成熟 / 无阶段（q10）；**调整 / 收缩 / 初创期仍和全体比**——q8 全阶段同阶段比实测抹平了弱势：A 股收缩期 B- 及以上 4% → 56%、美股调整期 20% → 40%、港股初创期 13% → 39%，q10 还原到全体口径的数字，成长 / 成熟 / 无阶段不变；依据 `GET /quant-research/diagnostics/whatif` 反事实；无阶段的金融股自成一组）；各阶段分布存在 distributions 表 `("_all", "_overall:<阶段>")`，样本外按需计算也读它；`Overall.text` 写「同为成熟期的公司 后 37%」。各维度等级仍是板块内可比。
> **EBIT / EBITDA 用经营利润口径**（q9，`inputs._operating_basis`：FMP 的 ebit / ebitda 含营业外收益，WDC 一年约 54.5 亿；A 股 / 港股没有该字段原样）；**利息支出报 0 但负债超过 EBIT 的 25% 视为数据缺口、该项不参与**（AAPL 最新财年 FMP 报 0）。
> **利息保障倍数在净利息收入为正（利息收入 ≥ 利息支出）时记上限 100**：现金多于负债的公司（如 CRWD）不能被「EBIT ÷ 利息支出」误判成勉强付得起。
> 响应 `Dimension.weight_pct` = 这一维在综合分里的实际占比（按可用维度归一，iOS 综合分解释里显示）。
> **财务稳健五项**（`metrics._stability`）：净负债 / EBITDA、利息保障倍数、流动比率、现金可支撑年数、经营现金流 / 净利润。**经营现金流 / 净利润封顶 100%**（q9，`CFO_NI_CAP`：超过 100% 只说明利润全有现金支撑，科技股常因股权激励 / 折旧加回达 150%+，不封顶会让苹果这类 114% 的公司排到板块中位 160% 之后拿 D-；实测 21 家大型科技股里苹果该项排位 38 → 60）；界面写「≥100%」。**「没有压力」一律记最好值、不当缺失**
> （净现金记 0、没有利息支出记 100、自由现金流为正不烧钱记 10 年上限），否则无负债公司反而不参与评分；有净负债而 EBITDA ≤ 0 按最差计；净利润为负时现金含量不参与。
> 金融股整维不适用（`financials_balance_sheet`）；A 股 / 港股报表没有流动资产 / 流动负债与利息支出，这两项在 `markets` 登记为无数据源。
> 测试里 `distributions.json` 快照早于该维度，`test_builder._synthetic_stability_dists` 造了**合成**的稳健分布（仅供测试 / golden，不代表真实板块）；真实分布由批量任务重算。
> 上线前须在真实数据上跑一遍批量，看综合等级分布有没有整体漂移、成长股与成熟板块有没有被误伤（离线只验证了逻辑，没验证分布）。
> **同阶段排名**（2026-10-10，`GET /quant-research/{market}/stage-ranking?stage=&symbol=&score=`，`quant_research/ranking.py`；iOS 点企业阶段弹层底部 `QuantStageRankingSection`）：列出该阶段综合分前 30 家 + 本股名次（样本外股票按它自己的综合分估算、标「≈」）。只陈列本模型结果、不是推荐榜：放在阶段解释里、不做独立 tab / 榜单页，文案带「不代表公司好坏的定论，也不构成投资建议」。整阶段排序数据 Redis 缓存 6 小时（`quant:{market}:stage_rank:{方法版本}:{批量日期}:{阶段}:{语言}`，批量日期取 `batch.latest_key`，新一天批量后自动换键；本股名次每次现算），App 本机内存再缓存 30 分钟（`StageRankingCache`）。点其中别的公司用全屏的 `StockAnalysisCover` 打开它的分析（自带一份 ChanViewModel、不覆盖当前详情页；免费额度规则同分析 Tab）；**已经在全屏页里再点就原地换股票**（环境值 `openStockAnalysis` + `.id(target)` 整页重建），不要再叠一层全屏页——每层都是完整详情页 + K 线图，叠两三层就闪退过。
> **基本面动向雷达**（2026-10-10 起，后端第一步；设计见 `docs/superpowers/specs/2026-10-10-fundamental-trend-radar-design.md`）：每只股票批量时算一份**动向事实**（`quant_research/trend.py` → 响应 `trend` 字段，不是评分、不进综合等级）：本财年 EPS 一致预期近 7 天（自有快照）/ 30 / 90 天（复用 EPS 修正维度的值）变化率，以及最近一季 vs 上一季（季度序列整体往前挪一季重算同一套指标）营收同比 / 毛利率 / 经营利润率 / 自由现金流利润率的百分点变化。
> `GET /quant-research/{market}/trend-radar`（`trend_radar.py`）按规则挑「预期上调」（7 天 ≥2% / 30 天 ≥5% / 90 天 ≥10%，分析师 ≥3）与「质地改善」（披露 90 天内、经营或现金利润率 +1pp、四项至少两项变好且无一项变差超过 3pp）放进 7 / 30 / 90 天三圈；门槛随响应返回给推导说明。只陈列事实、不排名次（此前「不做基本面并列视图」的规则由用户 2026-10-10 决定对这一模式放开）。
> **评级改善**（2026-10-10，App 里代替「质地改善」）：我们自己的综合等级在**同一评级方法**（`methodology_version`）下，比窗口（7 / 30 / 90 天）里最早一个评级日至少升 `RATING_MIN_STEPS`（1）档，按最小窗口放圈（`trend_radar.rating_item`）；
> 数据来自 `repository.trend_grade_history`（只取 payload 里等级 / 分数 / 版本四个 JSON 字段，不读整份）；**跨方法版本不比较**，池子里超过 `RATING_BULK_RATIO`（30%）的有评级股票同时升档视为全员重评、整类丢弃（同 `grade_events.BULK_DAY_RATIO` 的思路）；
> 响应 `kind="rating"`，条目带 `rating`（from / to 等级、升几档、综合分变化、对比的评级日），`magnitude` = 升的档数 + 综合分涨幅的零头（< 1），不依赖 `trend` 事实；缓存键升 `trend_radar:v4`。
> **冷启动 / 局限**：评级方法每次升级后历史从零开始，**刚升级时这一类会是空的**（q7~q11 两周内改了五次，当前版本历史很短）；A 股 / 港股评级历史比美股更短。后端的 `quality`（质地改善）类别保留给旧版 App，新版 App 的下拉框只有「预期上调 / 评级改善」（`QuantTrendKind` 只有这两个）。
> **高价值筛选**（2026-10-10）：每个条目带 `good`——综合等级达到本市场「好股票」门槛（与信号雷达**同一套自适应规则** `signal_radar.quality_view.choose_cutoff`：本市场有评级公司的前 25%、至少 8 只、不低于 B、整档纳入；响应 `good_grade` 回传）、`magnitude`、`sector`（`sectors.load_sector_tags` 的雷达行业 key，与雷达顶部行业横条同一套）。每类达标的与未达标的**各取 60 个、互不挤占**；缓存键升 `trend_radar:v2`。
> iOS：header 右侧「精选 · B 及以上 / 全部 · 含未达标」切换（`SignalRadarViewModel.trendOnlyGood`，默认精选；旧后端没有 `good` 时不筛）；**点顶部行业横条 / 行业面板筛选动向雷达**（`trendItems` 按 `sectorFilter` 过滤，此前动向模式下点行业没反应）；`trendItems` 按「综合等级高 → 低、同等级变化大 → 小」排好，画布最多画 `ringFieldCap` 个时先留最好的；分段控件上的数字是筛选后的个数；筛选后为空时提示「点精选切到全部」。推导说明（`TrendDerivations`）补了「颜色深浅」「气泡大小」「精选」三步。
> **iOS**（第二步；2026-10-10 起 App 里叫「基本面雷达」——下文多处仍写「评级雷达」指它，原「市场雷达」改叫「缠论雷达」；分析师评级另做成新的「评级雷达」，见下条）：点页面标题「缠论雷达 ▾」的下拉菜单切换「缠论雷达 / 评级雷达」（`flowTitle`，标题文字即当前雷达；菜单**只有这两项**，原来第三项「这一页怎么读」去掉了——流程图只在首次进雷达时自动展开一次、新手导览在学习页可重看；`SignalRadarViewModel.trendMode` / `exitTrend()`）。**指数选择两个雷达共用**：市场分段条里选中的那一段下面一直写当前指数名（评级雷达不再顶替成「基本面动向」），点它换指数**不会退出评级雷达**，评级雷达只看该指数的成分股（`GET /quant-research/{market}/trend-radar?universe=`，`universe` 为信号雷达的键或 `watchlist`；成分股用 `resolve_constituents`、自选读用户自选；「好股票」门槛也按这个池子重算，与雷达基本面名单同一口径；自选不缓存，其余缓存键 `trend_radar:v3:…:{指数}:…`），切回缠论雷达时若指数变了会补一次加载（`exitTrend`），画布**沿用缠论雷达同一套**（`fieldDecoration` 同心圈 + `layoutRingField(gradeRings: 近1周/近1月/近3月, ringScales:)`；**圈的大小按各圈条数分配**（`ringScales(counts:)`，面积约与条数成正比、相邻环至少隔 0.15，圈带不放宽、放不下先缩气泡——A 股预期上调曾 22 只全在近 1 周，固定内圈只画得下 1 只；缠论雷达仍是固定 1/3·2/3·1） + `RadarBubble`）：条目转成 `RadarSignal`（`trendSignals`：ring_days 7/30/90 → 内 / 中 / 外圈，**颜色深浅 = 变化幅度、大小 = 综合等级**（2026-10-10 起，此前是反过来的：大小 = 变化幅度三档、颜色三档深浅）——`trendSignals` 把变化幅度（`magnitude`，入圈门槛的几倍，跨圈可比）在当前画出来的同类公司里取百分位放进 `RadarSignal.strength`，`trendColor(kind, depth:)` 直接用**缠论雷达那条不透明渐变**（`bubbleColor(side: "buy", depth: 0.15~0.95)`，浅粉 → 深红；曾用红色加透明度、发灰发透，已改）；直径由 `quantGrade` 查 `trendDiameter(grade:best:worst:)`——**按当前画出来的这批公司的等级范围拉伸**（最高 96 → 最低 48，中间按名次均分；精选后多半只剩 A- / A / A+，按绝对档位每档只差几个点看不出，`layoutRingField` 对 `side == "trend"` 的气泡走这条，缠论雷达不受影响），画布**最多画 12 个**（`trendFieldCap`，其余在「查看全部」名单里），字母 = 综合等级；**颜色和缠论雷达一致**（用户 2026-10-10 要求，放开此前「不用红绿」的规则）：同一个红 `Theme.up`，两类动向靠分段控件区分、不再各用一个色；气泡带 `polished`（左上高光 + 细白边）。类别（预期上调 / 质地改善）是**画布左上角的下拉框**（`trendKindMenu`，选项后面的数字是当前精选 / 行业筛选下的个数；以前是顶部分段控件）；点气泡进个股「基本面研究」分段；「查看名单与变化」→ `TrendListSheet`；推导 `TrendDerivations`（门槛读响应 `thresholds`）。
> **三个雷达 + 红绿两侧**（2026-10-10）：标题菜单现为「缠论雷达 / 基本面雷达 / 评级雷达」（`SignalRadarViewModel.trendFlavor`：`fundamental` / `analyst`，`enterTrend(_:)`；两者共用指数、精选、行业筛选、画布与气泡）。
> **基本面 / 评级雷达的圈改为近 3 天 / 1 周 / 1 个月**（2026-10-10；后端 `trend_radar.RATING_RINGS=(3,7,30)`、`analyst_radar.RINGS=(3,7,30)`，评级历史只取最近 35 天，ring_days = 3 / 7 / 30；预期 / 质地旧类别仍是 7 / 30 / 90）；等级变化气泡最后一行写「B → A-」（`RadarBubble.gradeText`），不再只写现在的等级。
> **基本面雷达只有「等级变化」一类**（2026-10-10 起 App 不再看盈利预期，只用我们自己的综合等级；后端 `estimates` / `estimates_down` 类别保留给旧版 App）（`QuantTrendKind`：**等级变化**（rating + rating_down，我们自己的综合等级，原「评级改善」改名，避免和分析师「评级」混淆）；评级雷达只有「评级变动」一类（`rawKinds` = analyst_up + analyst_down 放一起，红绿按条目，只有一类时画布左上角不做下拉）；后端 `trend-radar` 的 `estimates_down` / `rating_down` 与上调侧同一套门槛（`rating_item(down=True)`、`estimates_item(down=True)`，缓存键 `trend_radar:v6`）；下调侧的「精选」= 现在或原来达标（掉出门槛的也算）。
> **评级雷达**（分析师评级，`GET /signal-radar/analyst-radar?market&universe`，`signal_radar/analyst_radar.py`）：复用 `analyst_events` 的 FMP `grades` Redis 缓存与后台补拉，窗口 7 / 30 / 90 天里各券商（同一家只算最新一次）上调家数 − 下调家数，>0 进 `analyst_up`、<0 进 `analyst_down`（同一只股票可两边都有），按最小窗口放圈，`magnitude` = 净差 + 近度零头；`good` 同 `choose_cutoff`；**只美股**（其它市场 `supported=false`，App 提示暂无），`pending_symbols` > 0 时 App 每 6 秒静默重拉（最多约 1 分钟）。接口只读缓存，**不要**在请求里同步逐只拉 FMP。
> **颜色**：红 = 向好的一侧（上调 / 上升），绿 = 向差的一侧（下调 / 下降），渐变用缠论雷达买 / 卖同一条（`trendColor` 按 `QuantTrendKind.isDown` 选 `SignalFormatting.radarColor` 的 buy / sell；合并类按条目自己的后端 kind 上色 `trendColor(raw:)`，图例画红绿两条），只表示方向。词典新增「分析师评级」（中英）。
> **雷达预热，用户请求只读缓存**（2026-10-10，`signal_radar/trend_warm.py`）：基本面雷达 / 评级雷达的慢活都在后台——`trend_warm_loop` 随信号雷达预热调度启动（启动后先跑一轮，之后每小时），遍历 `all_universes()`：基本面雷达 `get_trend_radar(scope=指数)` 写 Redis（6 小时，新一天批量换键），美股再 `cached_analyst_radar(refresh=True)` 重算评级雷达（Redis `signal_radar:analyst_radar:v2:{market}:{scope}`，补拉完整 2 小时 / 还有 pending 只缓存 1 分钟）并顺带触发券商数据后台补拉；全市场原料另有进程内 30 分钟缓存（`trend_radar._market_inputs`）。自选因人而异、不预热也不缓存，仍现算。**不要**让用户请求去读全市场评级历史或逐只拉 FMP。
> **启动数据**：新增落库字段用 `scheduler.PAYLOAD_TAG`（当前 t1）——最近一天结果缺 `trend` 时自举补跑一次全量（不升 METHODOLOGY_VERSION），所以上线即有数据，不用等几个月；A 股 / 港股没有外部预期趋势，30 / 90 天预期变化要等自有快照攒够（约 11 月起），质地改善上线即有。
> **q11（最后一轮规则改动，2026-10-10；之后只验证不再改规则）**：① 成对高度重复指标（`scoring.REDUNDANT_PAIRS`：fcf_m↔fcf_sbc_m、ebit_yoy↔ebitda_yoy、ebit_fwd↔ebitda_fwd，同维度秩相关 ≥ 0.9）两项都参与时各减半权重；
> ② 美股净利润剔除大额营业外项目（`metrics._adjusted_net`：报表 EBIT 与经营利润之差 ≥ 经营利润绝对值 25% 才剔除，扣税后从净利润减，税率取实际 0~35%、缺失 21%；净利率 / ROE / ROA 共用，`MetricValue.meta.adjusted`；`inputs._operating_basis` 保留 `ebitReported`；A 股 / 港股无此字段不受影响）；
> ③ 综合分先把各维度分换成全体百分位再加权（`scoring.composite(dim_dists)`，分布存 distributions 表 `("_all","_dim:<维度>")`，缺分布时退回原始维度分；一票否决仍看维度原始分 < 20）。
> 效果依据：统一尺度反事实秩相关 ≥ 0.986；旧「已知局限」②③⑤由此解决，⑥ 经 `/diagnostics/panorama` 的 `by_stage` 验证不成立（成长期盈利能力没有系统性偏弱），不再追加按阶段取舍盈利能力权重。
> **已知局限（q10 定版，2026-10-10 用线上诊断统计验证过，要改规则先用 `/quant-research/diagnostics*` 的统计论证、不要凭单只股票）**：
> ① 阶段判定对分拆 / 并购 / 重述造成的季度序列断点敏感（WDC 同比被压成 13.4% 误判成熟期；美股同比极端 1.1%、A 股 4.3%、港股 7.4%，A 股 / 港股大多是真实剧烈波动、分不开真假，所以没加财年兜底）；
> ② 净利率 / ROE / ROA / EPS 仍是 GAAP，含一次性收益（美股约 3.3% 的公司净利率比 EBIT 利润率高 10 点以上，A 股 0.3%、港股 1.2%）；
> ③ 各维度的「名义占比」不等于「对排名的有效影响」：成长维度有效影响约为名义的两倍，美股估值只有约 5%（估值与成长 / 动量 / 盈利负相关、互相抵消），财务稳健约一半；统一尺度反事实秩相关 0.986~0.990、≥3 档变化仅 0.3%~0.8%；
> ④ 经营现金流 / 净利润封顶 100% 后 69%~87% 的公司并列在上限（接近二选一，按并列取平均位次处理）；A 股 / 港股 EBIT 没有经营利润口径；
> ⑤ 同维度内百分位秩相关 ≥ 0.9 的重复指标：fcf_m 与 fcf_sbc_m（0.974）、EBIT / EBITDA 同比与预期增速（0.91~0.97）；
> ⑥ 成长期公司盈利能力里 GAAP 回报类指标（ROIC 等，约占该维度 57% 权重）对烧钱成长的公司不利，盈利能力没有像估值倍数那样按阶段取舍权重（待 `/diagnostics/panorama` 的 `by_stage` 数据论证）。

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
  编译：`cd rust/czsc && uvx maturin build --release -i python3.13`（约 10 分钟，产物 `target/wheels`）；**部署**：`Dockerfile` 多阶段——`czsc-build` 阶段（rust:1.90-slim-bookworm，与运行镜像同 glibc）编译 `rust/czsc`，运行镜像 `uv sync --frozen` 后用该 wheel `--reinstall --no-deps` 覆盖 PyPI 版，并断言 `dp_scan_bs / dp_structures / dp_macd` 存在（出问题让构建失败，不悄悄退回慢路径）。层缓存只跟 `rust/czsc` 内容有关，改应用代码不重编（首次约 10 分钟）。不要把本地编的 wheel 直接拷进镜像：它是 manylinux_2_39，Debian 12（glibc 2.36）加载不了。`railway.json` 的 watchPatterns 含 `rust/**`。
  `dp_trend_legs_V261001`：趋势前提（最后两个已确认中枢依次下移/上移、价格已离开 B）+ 价格越过 b 段终点（创新极值）+ b / c 段原始量（价差·量能·时长·起止时间；**不在 Rust 里算 MACD**，面积由 Python 用下面那条 MACD 序列按起止时间求和）。
  Rust 只输出**原始量**，是否背驰 / 强弱分档仍在 Python 的 `leg_metric`（保持度量可切换、API 统一）。严格口径的事件通过 `BsEvent.legs` 带着它走。
  中枢分组完全复刻 czsc `get_zs_seq`，且**只用已确认的笔**（`bars_ubi.len() < 5` 时排除最后一笔，与 czsc `zs_list` 同口径）。
  **两路径一致性**：同一时刻同一份结构上，Rust 信号与 Python 参考（`_in_trend` / `_trend_legs` / `leg_force`）逐位一致——51 只日线 11347 个快照零差异，
  回归测试 `tests/services/chan/test_dp_legs_parity.py`（标准 czsc 下自动跳过；改任一边的取法都会报警，已验证人为改坏会失败）。
  **端到端有一类已知、可解释的差异**：czsc 默认只留最近 50 笔（`max_bi_num`），Python 路径用「跑完全部数据后的最终结构」评估，最早一批事件缺中枢历史；
  Rust 在事件当时看到完整历史（点时刻，更准）。51 只样本里 20 个差异全部落在最终结构前段（距首笔 34~393 天），之后的信号两路径完全一致。
  **MACD 一律复用 czsc 自带的 TA-Lib 兼容实现**（Rust `calc_macd`，由 `dp_structures` / `dp_macd` 暴露，不再自己写 EMA）：EMA 以前 N 根简单平均作种子，数据不足的前 33 根记 0，柱 = 2×(DIF−DEA)（国内软件口径）；基于 czsc 的 `bars_raw`（比输入少第一根 K 线），Python 侧 `czsc_adapter.czsc_macd`，不要改回 `calc_macd(bars)`。标准 czsc 下 `divergence.calc_macd` 的 Python 回退与 TA-Lib 逐位一致（对照过 TA-Lib 0.8）。与旧自写实现（首价作种子）相比，面积比中位数差 0%，1336 个真实事件仅 4 个（0.3%）背驰判定翻转，全在 b 段处于最初 12~33 根的预热区。
  **逐根扫描与结构提取整段在 Rust（自编译 czsc 才有，标准版自动退回 Python 实现，结果一致）**：
  `dp_scan_bs`（`rust/czsc/crates/czsc-python/src/dp_scan.rs`）一次调用完成建 K 线（直接解析时间字符串）→ 逐根推进 → 提取买卖点事件 → 记笔完成 / 成笔时刻，
  计算期间释放 GIL；`dp_structures`（`dp_structures.rs`）一次调用完成建 CZSC + 提取合并 K 线 / 分型 / 笔 / 笔级中枢 + MACD，只返回纯数据，Python 的 `czsc_adapter._from_native`
  只负责实例化数据类（保持「相邻笔共享端点分型对象」「分型左中右 K 线是独立对象」的对象关系）；`dp_macd` 与 `divergence.calc_macd` 逐位一致。
  入口 `czsc_adapter.build_structures` / `czsc_signals._scan_native`，出任何错都退回原实现。
  对照与守护：`test_dp_scan_parity.py` / `test_dp_structures_parity.py`（含整条 analyze 两路径结果相等、MACD 逐位相等、对象关系、出错退回，均验证过人为改坏会失败）；
  真实数据 10 个数据集（美股两个年代 / A 股 / 港股的日线，三市场周线，三市场 30 分钟线）共 1042 只结构 + MACD + 整条分析零不一致，842 组整段扫描零不一致。
  **性能（2094 根日线一次严格口径分析）：190ms → 73ms**，其中 84% 是 Rust 原生计算。**改动这些函数必须先改 Python 参考再对照，不要只改一边。**
  **二 / 三类、`_holds`、去重不迁 Rust**（见下条）；二类实测无超额收益（四个样本合并 10 日 -0.29%，t=-0.6；一类 +2.7%、三类 +2.6%），但雷达**只陈列事实**，二类照常展示，不降级、不隐藏。
  **不迁二 / 三类到 Rust（2026-10 实测决定）**：一次严口径分析约 85ms，其中 czsc 内核逐根推进约 60%、结构转换约 17%，
  `generate_all_signals`（一类作废 / 二类 / 三类推导 / 同笔去重 / 成立日）合计约 1ms（1%），迁走收益≈0；而二类依赖一类事件，
  czsc 触发有「状态翻转才记一次」的细节，Rust 里逐位复刻风险大。二 / 三类、`_holds`、去重留在 Python。
  以后若要再加 Rust 信号，**每加一个先写 Python 参考 + 逐位对照测试，再切换**，并先用 profile 证明有收益。

**买卖点口径（`signal_policy.py`，统一接口 + 多套实现）**
- 「什么算买卖点」有多套口径，都实现 `SignalPolicy`（`czsc_families` / `assemble` /
  `split_unconfirmed` + 名称、版本、中英文案），在 `SIGNAL_POLICIES` 注册，按名字 `get_policy(mode)` 取。
  analyzer、`/chan/analysis`、`/chan/sub-level`、信号雷达（快照 / 自选 / 示例日）都只传 `mode`、走接口，
  **不要**写 `if mode == ...` 分支。**App 里用户自己切换口径**（2026-10-07 起，「我的 → 买卖点口径」（一级页，2026-10-09 起）→ `SignalModeSettingsView`，严格 / 中等 / 宽松三选一并写明区别；选择存 UserDefaults，`SignalMode.current()` 读取，默认 medium；雷达、详情、次级别都带同一个 `mode`；线上旧版 App 仍请求 loose）。
  **三套口径定时任务都预热**（`scheduler._modes()` = loose / medium / strict，示例日中等优先）；改任一口径的判定须升它的 version，改 App 文案时 `SignalModeSettingsView` 的三段说明要同步。
  `medium`（`mid1`）= 严格 + 盘整里的背驰也算一类（`consolidation=True`，约 2 倍信号）；`GET /chan/signal-modes` 列出全部口径（App 现用本地文案）。
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
    **盘整背驰不算一类**（严格口径）；「中等」口径（`medium`，`mid1`）放宽：不满足两中枢趋势前提的 czsc 一类事件也算，沿用 czsc 笔级力度判定，仍受「只落已完成的笔 / `_holds`」约束，15 只 A 股两年 37 → 74 个（宽松 230）；下一次同向笔又创新低 / 新高的一类作废（`_holds`，背驰段还在延伸）。
    **中枢 B 延伸上限**（std10，`CHAN_PIVOT_EXTEND_LIMIT`，默认 9，0=不限）：缠论原文中枢延伸到 9 段即升级为更高级别中枢，原级别「a+A+b+B+c」不再成立；
    信号时刻 B 已有元素（笔）数（`signals.pivot_b_size`，不看信号之后才延伸的部分）超过上限的一类不要。40 只美股近两年 60 个一类里丢 11 个
    （含 DXCM 2026-04-29 一买，B 内 12 笔）；被丢与保留的信号 20 日方向调整收益无可区分差异（+5.3% n=9 / +3.2% n=47），所以这条是**原文依据、不是收益依据**，
    觉得误伤就调大或设 0。
    **黄白线回抽零轴**（`CHAN_ZERO_PULLBACK`，默认空=不要求；`signals.zero_axis_pullback`）：缠论原文的辅助条件——b、c 之间（B 震荡期间）DIF 要回到零轴附近，
    c 段才算重新起算的一段力度。0=回到零轴，0.2=回落到 b 段 DIF 峰值 20% 以内（版本号带 `.zp<值>`）。46 个样本里 0 的口径只剩 20 个、0.2 剩 31 个，
    被滤与保留的 20 日收益也无可区分差异，所以**默认不开**，要开先在更大样本上看信号数是否可接受。
  - 一类的背驰（std6 起）= 缠论原文的 **c 段（离开 B）对 b 段（A、B 之间）**比力度（`signals._trend_leg_divergence`），
    b / c 段按笔级中枢取（`_trend_legs`）：czsc 的相邻中枢首尾相接（A 结束 = B 开始），**A 的最后一笔就是离开笔，算 b 段开头**；**离开笔** = 与中枢区间有重叠、沿趋势方向、终点越过边界的最后一笔（`_exit_stroke`），b 段（对 A）、c 段（对 B）都从各自的离开笔起算、含离开笔。czsc 会把离开笔吸收进中枢，**不要**从「中枢最后一个元素的终点」起算（曾因此 c 段被砍短、背驰几乎必然成立，见 tests 回归用例）。另需信号价越过 b 段终点（创新极值）。不要改回「末笔对前一同向笔」。中枢没有笔明细、或该度量缺数据（没传 MACD）时退回 czsc 笔级判定。
  - **背驰度量可插拔**（std7，`chan/leg_metric.py`，`DivergenceMetric` 接口）：`macd_area`（默认，原文 MACD 红绿柱面积）/ `force`（价差·量能·时长）。
    切换只改配置 `CHAN_DIVERGENCE_METRIC`，版本号 `std9.<度量名>` 自动隔离雷达缓存。**API 字段永远同一套**：`price_ratio / volume_ratio / length_ratio`
    任何度量都填，`area_ratio` 仅 MACD 面积度量填；强弱分档由度量自带的 `classify(primary_ratio)` 给出，各度量阈值各自标定：`force` 沿用价差比 0.6 / 0.8；`macd_area` **不分档**（背驰成立一律 `medium`；两个年代约 2000 个信号实测面积比与后续收益无关：秩相关 -0.02 / +0.03，p=0.52 / 0.38，背驰组对照组差不显著；原文也只有「面积更小即背驰」的二元标准）。**不要**再按面积比设阈值或分强弱档，除非有新的实证依据。
    `macd_area_avg`（可选，默认不用）= 面积按时长归一（每根 K 线平均面积）：累计面积正比于时长，c 段常比 b 段短得多，面积比易偏小（NVDA 2025-10-29 一卖
    c 段 5 个交易日对 b 段约 4 个月，面积比 0.06、归一后约 0.5）。40 只美股 57 个一类：两种口径 38 个相同、各自独有 10 / 9 个，20 日收益无可区分差异，
    所以没有换默认；换度量须升版本（版本号带度量名自动隔离）。
    新增度量：实现 `compare(c, b)` + 注册进 `DIVERGENCE_METRICS`，不要在判定流程里写 `if metric == ...`。
  - 同一笔终点同时命中二类与三类只留一个（三类 > 二类，与宽松口径同）。
  - 二类 = 一类后的第一次回落 / 反弹不破一类极值（`_derive_type2`，一类所在笔 i 的 i+2 笔）。
  - 三类 = 离开中枢后的第一次回落 / 反弹没有回到中枢（`_derive_type3`，复用 `pivot_phase` 的
    `_is_breakout` / `_classify_retrace` 配对，与「确认三买」同源）。
  - 严格口径**不要**用 czsc 的 `cxt_second_bs_V240524`（按端点价格重叠、不要求先有一类）或
    `cxt_third_bs_V230318`（5 笔局部中枢 + SMA34 均线过滤）——都偏离原文；实测 8 只股票一年
    由 62 个降到 9 个，全部符合标准定义。也**不要**换成 `tas_macd_first_bs_*` 这类纯 MACD 信号。
- 背驰口径统一为**一类趋势背驰**（2026-10-05 起，严格口径）：c 段（离开中枢 B）对 b 段（A、B 之间）的 MACD 红绿柱面积比（缠论原文，
  `signals._trend_leg_divergence`），不分强弱档。图上标注（分别画 b 段、c 段两条粉线，比值标在 c 段上「趋势背驰 + 面积比」；**不要**连 b 终点 → c 终点的长线，会跨过整个中枢 B 长达数月）、一类买卖点、
  文字结论 / 形态推荐 / 走势展望 / 中枢阶段 / 缺口读到的「笔级背驰表」`result.divergences` 都是这一套：
  严格口径下 `analyzer` 在 `split_unconfirmed` 之后用 `signals.unify_stroke_divergences` 把它重建为只含一类趋势背驰（`policy.unify_divergences`），
  **不要**再让叙事等模块读价差·量能·时长的笔对笔背驰。同一个 b 段终点图上只留一条线（成立优先、同级取最新，`signals.leg_divergence_marks`）。
  API：`DivergenceResult.b_end_time/b_end_price` → `/chan/analysis` 的 `StrokeOut` 在对应一类信号所在笔上给
  `diverged=true / area_ratio / div_length_ratio / div_ref_*（b 段终点）/ div_b_start_* / div_c_start_*`；**面积比在 App 上写成百分比**（「趋势背驰 8%」），点开解释同时给时长比与价差比，并说明「面积是累计值、c 段常比 b 段短所以偏小」（NVDA 一卖 6% 里时长比就占 12%）；旧版 App 读不到新字段时退回「同向前一笔」作参照点。
  仍用价差·量能·时长力度口径的只剩：宽松口径（旧版 App，`unify_divergences=False`）与线段级背驰（`find_segment_divergences`，只在叙事里提一句）。
  改口径 / 背驰度量时，App 内教程（`lessons.json` 中英，背驰 / MACD / 三类买卖点）须同步改。
- **背驰术语一律用缠论原文**（2026-10 起）：只说「趋势背驰 / 盘整背驰」（`DivergenceResult.type`，API `StrokeOut.divergence_type` = `trend` / `consolidation`），
  **不要自造概念**（顶背驰 / 底背驰、笔力度减弱、「趋势可能转折」等都已去掉）。阶段标题 / 依据 / 图上标签 / 图元解释都按类型显示；
  歧义的地方（趋势背驰对应一类买卖点、盘整背驰不对应）只写在点开的解释里，不放标题。网页前端个别页面（`frontend/lib/chan-glossary.ts` 等）仍有旧叫法，未统一；iOS 教程 `lessons.json`（背驰 / MACD / 三类买卖点 / 走势级别）与 `LessonDiagrams` 已于 2026-10-05 对齐到本节与「买卖点口径」，**改口径时教程文字要一并改**（中英两份）。

**数据层（根治性，别在算法层补数据的锅）**
- **前复权**：`skills/kline.py` 全链路用前复权价（FMP dividend-adjusted 端点、Yahoo
  `adjclose` 按比例回调 OHL、东财 qfq）。缠论是纯价格几何，不复权/半复权会在除息、
  A 股送转日产生人为跳空 → 假分型/假笔/假缺口。缓存键带 `qfq` 命名空间。
- **日线固定分析起点（两年，2026-10 起）**：缠论的笔 / 中枢对「从哪根 K 线开始算」敏感——起点早几天就多出一笔，czsc 从第一笔往后
  给中枢分组，整条序列的中枢整体错开，早期买卖点会凭空出现或消失（MNST 2025-10-31 三买：起点 2025-09-19 没有、2025-10-01 有）。
  所以日线显示起点固定为 `chan/window.canonical_daily_start(截止日)` = 截止日 - 730 天、取当月 1 号（每月才变一次，K 线缓存键也稳定），取数 / 计算起点 `canonical_daily_fetch_start` 再往前一年作预热（同月按年平移，不减 365 天以免闰年差一个月）——没有预热时显示区第一年几乎没有买卖点（8 只样本严格口径 1 个，预热一年 7 个，预热两年仍 7 个）；
  详情页（`api/v1/chan.analysis_window`）、信号雷达（`_fetch_start`）、自选阶段（`watchlist_phases`）、次级别的大级别（`sub_level_service`）
  **共用这个取数起点**，用户所选起始日期只决定显示哪一段（`visible_from = max(用户起点, 固定显示起点)`），不再影响结构。
  测试 `tests/api/test_chan_window_alignment.py`。注意：固定窗口给的是**稳定而不是更对**——换固定起点早期分组会再变一次；改它须升雷达 `_mode_ns` 的窗口版本（当前 `win2y_wu1y`）。
  周线 / 30 分钟沿用旧口径：`ChanAnalyzer.analyze(visible_from=...)` 在可见起点前多取 warmup（周线 540 天 / 30 分钟 20 天）在完整序列上计算，再裁剪回可见窗口。
  裁剪时**笔与笔级背驰、线段与线段级背驰按下标平行，必须一并过滤**（下游 zip 依赖对齐）。
  czsc 要积累若干笔（一买>=5、三买>=7、二买>=15）才出信号，所以始终预热（`warmup_days` 参数已废弃被忽略）。
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
  通常在出现日左侧几根，也可能差几周，如 AVGO 三卖极值 09-22 / 成立 10-02）；iOS 图上从徽标价位水平向右拉一条细虚线、终点画小空心圆点并写「成立」标出成立日，点圆点或「成立」二字弹说明（`ChartElement.established`）
  （`ChanChartView.drawEstablishedMark`），列表行折叠时也写「图上 极值日」，两个日期都对得上。守护测试 `tests/services/chan/test_signal_out.py`。
- 强度：一类按 czsc 同一判据复算的力度比分档（基准 = max(前一个同向笔, 关键笔均值)，
  见 `signals._first_bs_force`），说明写出价差/量能/时长三项比值；
  二/三类 = 信号前**最近已结束**中枢的级别 + 余量（`_type23_strength`），尚未结束的中枢不参与。
- 用语统一（`pivot_phase.py` 与 App 流程图同一套）：状态 = 中枢形成 / 中枢震荡 / 离开中枢 /
  确认买卖点 / 背驰 / 转折；动作 = 形成中枢 / 突破 / 回落（向上离开后）/ 反弹（向下离开后）/
  回到中枢；ZG / ZD 对用户写「中枢上沿 / 下沿」。不用回踩、反抽、离开段、假突破（有测试守护）。
- 描述文案不出现 czsc 等第三方库名。
- **颜色语义（2026-10-05 起，iOS）：红 / 绿只给「已成立的买卖点」**（实心徽标 / 气泡 / 列表）。待确认候选一律灰色虚线、文字前缀「待」
  （图上「待卖3」），不带买卖方向色；中枢阶段标题（结论卡 / 自选标签 / 流程图）用中性蓝 + 方向箭头（`Theme.phaseColor` / `phaseArrow`），
  不写「结构偏强 / 偏弱」。以前三者都着红绿，同一页出现红色一买 + 绿色阶段标题 + 绿色虚线「卖 3」会被读成又买又卖（APP 2026-09-01）。
  结论卡底部有一行图例；「最新信号」格会显示同日或更新的待确认候选。`pivot_phase` 在没有对应信号时不写「接近三卖形态」，
  只说成立条件（「这一笔走完后仍没有回到中枢，才会成为三卖」）。
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

**均线与图表指标栏（2026-10-09）**
- 均线 `app/services/chan/ma.py`：按含预热的完整前复权**原始 K 线收盘**算简单移动平均（日线 / 30 分钟 5·20·60，周线 5·10·20），再按合并 K 线的 **`end_time`（所含最后一根原始 K 线）**对齐输出 `/chan/analysis` 的 `ma` 字段
  （`values["5"]` 等与 `merged_candles` 一一对应，不足周期为 null）。**不要**用合并 K 线的 `time` 对齐（那是缠论选的极值那根，可能早于最后一根，最右一根均线会停在几根之前）；均线在结构判断之前算，分型 / 笔不足提前返回时也带均线。
- EMA（12 / 26，TA-Lib 口径，与 MACD 同口径）和 BOLL（20 周期、2 倍**总体**标准差）在 `app/services/chan/indicators.py`，对齐方式同均线，接口字段 `ema`（形状同 `ma`）/ `boll`（upper / mid / lower）；默认关，指标栏里点开。
- iOS 图表下方是**指标栏**（`Views/Chart/ChartIndicator.swift`：`ChartIndicator` 枚举 + `IndicatorBar`），点一下开 / 关，选择存本机（只存用户明确选过的，没选过走 `defaultOn`；2026-10-09 起所有指标含均线都默认关）。
  **新增指标**：枚举加 case → 后端加按合并 K 线对齐的字段 → `ChanAnalysis` 加属性 + `IndicatorBar.isAvailable` 写何时有数据 → `ChanChartView` 里按 `vm.isOn(.xxx)` 画 → 词典补条目（中英）。新增指标默认关。
- **威科夫指标**（图上方右侧「对比」下拉框里，默认关；2026-10-10 起不再在图下方指标栏）：后端 `/chan/analysis` 的 `wyckoff` 字段（`app/services/wyckoff/overlay.py`，复用 `wyckoff/analyzer`，约 2ms，失败不影响主体）——只拿**可见窗口**（`visible_from` 之后）的 K 线分析，事件与交易区间按合并 K 线的 `end_time` 对齐成**下标**（App 直接按下标画，同均线思路）。
  **「对比」下拉框**（`ChartLegend.techniqueMenu`，竖屏详情页图例行最右、全屏图例末尾；分享长图里不放）：目的是拿别的看盘方法和缠论对照，目前威科夫 / SMC，**以后新增的对比技术加进 `ChartIndicator.comparisons` 即可**（`ChanViewModel.comparison` / `setComparison(_:)` 保证同时只开一个；这张图没有该技术的数据时不列出）；图下方的指标栏只剩均线 / EMA / BOLL，指标设置里也没有它们的页签。
  **点开威科夫（或 SMC）时把缠论图层（分型 / 笔 / 线段 / 中枢 / 买卖点 / 背驰）全部关掉，再点关掉时原样恢复；威科夫与 SMC 同时只开一个**（`ChartIndicator.hidesChanLayers`、`ChanViewModel.toggle` → `syncChanLayers`，开前状态只存内存；**重启后威科夫 / SMC 一律回到关、缠论图层回默认**，不跨重启保留它们的开关）。
  图上只画交易区间（浅棕色带 + 上下沿虚线）+ 事件代码标记（SC / Spring / SOS …，点标记弹说明，`ChartElement.wyckoff`），左上角数值行写阶段与区间上下沿；**不带操作建议、不带「买点 / 离场点」措辞**（网页端 `/wyckoff/analysis` 的 recommendation 与事件 description 里有这类词，**不要**搬进 overlay，`test_overlay_has_no_trading_wording` 守护）。
  **滚动识别多段结构**（`overlay.build_overlay`）：威科夫分析一次只认「量比最高的那个高潮」及其区间，视窗里大部分时间什么都没有（BABA 实测只剩 SC、AR）。所以价格收盘离开区间（超出 15% 区间宽度）后，从突破那根起再分析一遍找下一段，最多 `MAX_STRUCTURES`=4 段（接口字段 `ranges` 数组，阶段取最后一段）；一段里认不出结构就往后挪 `SCAN_STEP`=60 根再试；宽度不到支撑价 4%（`MIN_RANGE_WIDTH`，RKLB 实测 2.4%）或不足 `MIN_SPAN`=3 根的不算区间；每段区间与事件只画到突破为止（突破后重复的 SOS / SOW 是趋势里的放量，NVDA 实测 11 个）。
  **日线用固定两年窗口**（`canonical_daily_start`，与缠论同口径），不随用户所选起始日期变短——选了较晚的起点会让威科夫只看到几个月、识别不出结构。
  颜色用浅棕 `Theme.wyckoff`（避开红 / 绿与笔 / 中枢 / 背驰 / 均线已用色）。词典 17 条（威科夫 / 交易区间 / 15 个事件，`glossary.json` 中英），新手入门 `guide-app-detail` 已补指标栏一条。**已知局限**：事件的判定阈值（量比 1.6、前序趋势 12%）沿用网页端，未针对 App 的两年窗口标定。
- **SMC 指标**（图上方右侧「对比」下拉框里，默认关，2026-10-10）：后端 `/chan/analysis` 的 `smc` 字段（`app/services/smc/algo.py` 纯函数识别 + `overlay.py` 对齐合并 K 线下标，失败不影响主体），
  口径参照 LuxAlgo「Smart Money Concepts」与 joshyattridge/smart-money-concepts，只做有明确规则、能由 K 线直接算出的：
  ① 摆动高 / 低点（左右各 `SWING_LEN_BY_FREQ` 根：日线 10 / 周线 5 / 30 分钟 10，**右侧确认后才生效**）；② 结构突破 BOS / 转变 CHoCH（收盘越过最近已确认的摆动点，顺结构方向 BOS、逆向 CHoCH，每个摆动点只被突破一次）；
  ③ 订单块（突破时取被突破摆动点到突破前反向极值那根 K 线的整根区间，收盘反向穿过即失效，**只画未失效的**，最多 6 个）；④ 公允价值缺口 FVG（三根 K 线缺口，中间那根实体须大于此前平均实体 2 倍，价格回到远端即填补，**只画未填补的**，最多 8 个）；
  ⑤ 等高 / 等低点（相邻小级别摆动点之差 < 0.1×ATR）；⑥ 流动性扫荡（影线越过未被收盘突破的摆动点、收盘回到原侧）；⑦ 溢价 / 折价区 + 50% 中位（最近摆动高低点随新高新低延伸）；⑧ 强弱高低点（同一组极值，结构向下高点为强、向上低点为强）；⑨ 前日 / 周 / 月高低点（日线画周、月，30 分钟画日、周，周线画月）。
  **摆动长度的校准**（2026-10，8 只美股 / 港股 / A 股近三年日线）：长度 3~5 时两年里有 25~40 次突破、一屏全是线，10 时每只约 9~15 次，所以日线取 10；LuxAlgo 默认的「主结构 50 / 内部结构 5」在两年日线上要么太稀要么太密，这里只取一级。改长度须同步改推导 / 说明里写的数字。
  **只陈列位置与事实**：说明文字以「只标出位置，不是买卖信号」收尾，不出现买卖导向措辞（`test_overlay_has_no_trading_wording` 守护；订单块不叫「入场区」，溢价 / 折价不是「贵 / 便宜」，强弱高低点只是按结构方向的命名）。
  iOS：图层勾选在「对比」下拉框选了 SMC 后多出的「SMC 显示内容」子菜单里（`SmcLayers`，存本机；默认只开结构 / 订单块 / 缺口，其余按需，全开会铺满整张图），点标记 / 线 / 方块看解释（`ChartElement.smc`，`ChartElementExplainer.smc`），颜色向上蓝 `Theme.smcBull`、向下琥珀 `Theme.smcBear`、中性 `Theme.smcNeutral`（避开红绿）。词典 10 条（SMC / 结构突破 / 结构转变 / 订单块 / 公允价值缺口 / 等高低点 / 流动性扫荡 / 溢价与折价 / 强弱高低点 / 前周期高低点，`glossary.json` 中英），新手入门 `guide-app-detail` 已补。
  **影线用原始高低点**（2026-10-10）：SMC / 威科夫按**原始 K 线**算，而图上是缠论去包含后的合并 K 线——合并 K 线的 high / low 是按方向合并出来的（上行取高点最大、低点最大），比真实影线短，结构线 / 订单块的边会飘在影线外（NVDA 订单块约一半超出所在合并 K 线）。
  所以 `/chan/analysis` 的每根 `merged_candles` 多带 `raw_high / raw_low`（`chan/raw_extremes.py`，按 `MergedCandle.raw_start..raw_end` 取所含原始 K 线的最高 / 最低，三只股票 1362 根逐根核对过下标偏移为 0），打开 SMC / 威科夫时 App 用它们画影线并参与纵轴范围（`ChanChartView.wickHigh / wickLow`），缠论图层开着时画法不变。**不要**改成在合并 K 线上算 SMC：突破只有约一半相同、FVG 会少一半多（0700.HK 7 → 3）。
  **改识别规则 / 阈值时，说明文字（`ChartElementExplainer.smc`）与词典条目（中英）一起改**。**已知局限**：规则按两份开源实现取舍、没有针对 A 股 / 港股单独标定；FVG 的 2 倍实体阈值、等高低点的 0.1×ATR 沿用 LuxAlgo 默认值。
- 30 分钟周期可在条件页选，**会员功能**（示例股除外，与次级别确认同一权益）；`ChanViewModel.apply` 没指定周期时 30 分钟回到日线，避免自选 / 雷达入口沿用它绕过门禁。
- **截屏后自动生成的分享图**（`Share/WindowCapture.swift`）：App 收到系统截屏通知后自己再截一张前台窗口，**不含状态栏（系统 window 截不到）、顶部导航栏（返回 / 标题 / 分享 / 收藏）和底部 TabBar**，再拼品牌脚与二维码。导航栏、TabBar 都是「当前真的可见才裁、没有就不裁」（全屏图表页 `fullScreenCover` 盖在上面时下层导航栏看不见，按最上层被呈现的控制器找；拿不准一律不裁——误裁会切掉内容、漏裁只多一条栏）。裁掉顶部后画布起点不在 (0, 0)，用显式平移取图。

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
