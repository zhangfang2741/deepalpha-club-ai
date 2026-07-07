# 美股供应链图谱（Supply Chain Graph）设计

> 日期：2026-07-07
> 状态：设计稿（待 review）

## 1. 背景与目标

构建一张覆盖**全美股（约 5000-6000 家上市公司）**的供应链知识图谱：

1. 对每家公司问「上游核心供应商有哪些」「每个供应商供应什么产品」；
2. 以企业为实体、产品供应为关系建图，由模型给出 0-100 的置信度；
3. 对置信度 < 60 的关系，取该企业对应的 SEC 提交文件分析供应链/商品数据，重新判断置信度，并在实体和关系上追加「线索列表」。

项目已有产业图谱模块（`app/services/graph/` + `graph_entity/graph_fact/graph_source` 模型 + `/supply-chain` 前端页），那是「文档驱动、证据落地」的 FinReflect 图谱。本需求与之**解耦**：以「公司」为中心、批量覆盖全市场、模型知识先行 + SEC 兜底增强，是一套独立子系统。

## 2. 关键决策（已与用户确认）

| 维度 | 决策 |
|------|------|
| 公司范围 | 全美股 ~5000-6000 家（最终愿景）；分阶段上线，先 S&P 500 验证 |
| 数据模型 | **新建一套独立表**，与现有产业图谱解耦 |
| 执行模型 | 单公司按需 + 批量后台 runner，复用同一套四步逻辑 |
| 第 4 步产出 | 线索 = 带立场的证据片段，只加不删；模型综合线索重打分 |
| 供应商粒度 | 每家 Top 5-10 核心供应商，产品供应记为自由文本 |
| 供应商解析 | 尽量映射到美股 ticker，否则存为命名实体 |
| 任务队列 | **Celery + Redis broker**（broker/backend 复用 Upstash Redis） |
| 任务管理 | 自建任务表 + API + 前端监控页 |
| 领域模型 | **复用 `giraffeai` 的 `GiraffeGraph`/`GiraffeNode`/`GiraffeEdge`/`GiraffeProperty`** 属性图领域对象作为计算层 |
| 持久化 | **方案一**：SQLModel 表持久化，`GiraffeGraph` 做领域/计算层，repository 层双向映射 |

## 3. 领域对象引入（GiraffeGraph）

`giraffeai`（`/Users/hanqing.zf/PycharmProjects/giraffeai`，内网 git `code.alipay.com/security_release/giraffeai.git`）中的 `src/core/domain/giraffe_graph.py` 提供属性图领域对象：

- `GiraffeProperty(name, value)` —— 单个属性，可哈希
- `GiraffeNode(node_id, node_type, properties: list[GiraffeProperty])` —— 节点
- `GiraffeEdge(src_type/src_id → dst_type/dst_id, edge_type, timestamp, properties)` —— 边，`generate_edge_id` 基于核心要素生成确定性 UUID
- `GiraffeGraph` —— 图算法集合：`sub_graph`(BFS 连通子图)、`page_rank`(个性化 PageRank 找关键节点)、`merge/diff`、`filter_nodes/edges_by_property`、`trim_to_token_limit`(喂 LLM 前按 token 裁剪)、`flat_nodes/edges`(转 DataFrame)、`to_dict`(camelCase 序列化)

**引入方式（不能整包安装 giraffeai）**：

`giraffeai` 含重依赖与内网依赖（`count_tokens` 依赖 `transformers`；`GiraffeLoggerUtil` 依赖 `antmcp.utils.tracer`、`env_util`、`project_util`；整体在内部 git）。整包安装既重又不通。因此：

- 新建 `app/services/supply_chain/domain/giraffe_graph.py`，**摘取** `giraffe_graph.py` 的 `GiraffeProperty/GiraffeNode/GiraffeEdge/GiraffeGraph` 四个类，保留其图算法与属性图语义；
- 替换内部依赖：
  - `str_util.generate_uuid_from_str` → 复制为本地 `app/utils/uuid_util.py`（仅 `hashlib`+`uuid`，零额外依赖）；
  - `count_tokens` → 用本项目已有 token 估算（tiktoken 优先，回退字符数/4），不引入 `transformers`；
  - `GiraffeLoggerUtil` → 替换为本项目 `structlog` 的 `logger.exception(...)`；
  - `networkx` / `pandas` → 通过 `uv add networkx pandas` 引入（轻量、纯 Python，`pandas` 已在仓库多处使用，需确认是否已声明）。
- 在该文件顶部以注释标注来源与改动点，便于后续与上游同步。

> 图谱语义约定（本子系统内）：
> - `node_type` ∈ `{"company", "supplier"}`（company = 上市采购方；supplier = 上游供应方，已映射 ticker 的 supplier 仍用 "supplier" 类型，但 `properties.ticker` 标明可交易标的）
> - `edge_type` = `"SUPPLIED_BY"`，方向 `supplier → company`（上游流向下游）
> - `timestamp` = 关系抽取/最近一次验证的秒级时间戳
> - 边 `properties`：`product`(自由文本)、`confidence`(0-100 int)、`confidence_source`(`LLM`/`SEC_VERIFIED`)、`status`(`active`)、`rationale`(模型理由)、`evidence_summary`
> - 节点 `properties`：`name`(规范名)、`ticker`、`aliases`、`resolved`(bool)、`is_listed`(bool)、`description`

## 4. 数据模型（SQLModel，新建，继承 `UUIDModel`）

> 字段语义对齐 `GiraffeNode/GiraffeEdge`，使 repository 层映射为薄层。`properties` 用 JSON 列承载 `GiraffeProperty` 列表。

### 4.1 图谱三表

**`SupplyChainNode`**（`app/models/supply_chain_node.py`）
- `node_id: str`（业务主键，索引唯一）：能映射 ticker 的用 ticker 大写（如 `TSM`），否则用规范名称的确定性 UUID（`generate_uuid_from_str(canonical_name)`）
- `node_type: str`（`company` / `supplier`）
- `name: str`（规范主名称，索引）
- `properties: JSON`（承载 GiraffeProperty 列表：ticker/aliases/resolved/is_listed/description）
- `first_seen_run_id: UUID | None`、`updated_at`
- 去重：按 `node_id` 唯一（ticker 优先）

**`SupplyChainEdge`**（`app/models/supply_chain_edge.py`）
- `edge_id: str`（确定性，索引唯一）：由 `GiraffeEdge.generate_edge_id` 基于 `(src_type,src_id,dst_type,dst_id,edge_type,timestamp)` 生成——幂等键，重跑 upsert 不新增
- `src_node_id: str`、`src_type: str`、`dst_node_id: str`、`dst_type: str`、`edge_type: str`（=`SUPPLIED_BY`）
- `timestamp: int`（秒级）
- `properties: JSON`（product/confidence/confidence_source/status/rationale/evidence_summary）
- `confidence: int`（0-100，冗余字段便于按阈值查询与索引）
- `confidence_source: str`（`LLM`/`SEC_VERIFIED`，索引）
- `last_run_id: UUID | None`、`updated_at`
- 索引：`(dst_node_id)`（按采购方查其供应商）、`confidence`、`confidence_source`

**`SupplyChainClue`**（`app/models/supply_chain_clue.py`）—— 第 4 步产出的线索（带立场证据片段）
- `edge_id: str | None`（挂到某条关系；索引）
- `node_id: str | None`（同时挂到关键实体）
- `source_type: str`（`SEC_10K`/`SEC_10Q`/`SEC_8K`）
- `document_url: str`、`section: str | None`、`filing_date: date | None`
- `snippet_text: str`（原文片段）
- `stance: str`（`SUPPORT`/`REFUTE`/`NEUTRAL`，索引）
- `confidence_delta: int | None`（模型给出的分数增减建议，可空）
- `run_id: UUID | None`、`created_at`

### 4.2 任务管理两表

**`SupplyChainRun`**（`app/models/supply_chain_run.py`）—— 一次批次或单次运行
- `run_type: str`（`single`/`batch`）
- `universe: str`（`sp500`/`nasdaq100`/`russell1000`/`full`，或单 ticker）
- `status: str`（`pending`/`running`/`paused`/`done`/`failed`，索引）
- `total: int`、`completed: int`、`failed: int`
- `params: JSON`（universe 过滤、模型名、阈值等）
- `started_at`、`finished_at`、`created_at`

**`SupplyChainTask`**（`app/models/supply_chain_task.py`）—— 单公司任务
- `run_id: UUID`（外键，索引）
- `ticker: str`（索引）
- `stage: str`（`DISCOVER`/`RESOLVE`/`SEC_VERIFY`，当前阶段）
- `status: str`（`queued`/`running`/`success`/`failed`/`retrying`，索引）
- `retries: int`、`max_retries: int`
- `celery_task_id: str | None`
- `error: str | None`
- `result_summary: JSON`（发现的供应商数、验证关系数等）
- `started_at`、`finished_at`、`created_at`

### 4.3 迁移

`uv run alembic revision --autogenerate -m "add supply chain graph tables"`，五张表一次迁移。

## 5. 四步 Pipeline（`app/services/supply_chain/`）

纯函数 + 依赖注入（LLM/FMP/SEC client 全部可 mock），Celery 任务在 `app/tasks/supply_chain.py` 编排。

### 5.1 discover —— 问供应商 + 产品 + 模型置信度
`discover_suppliers(ticker: str, llm) -> list[dict]`
- 一次结构化 LLM 调用，返回 Top 5-10 供应商：`{supplier_name, product_text, rationale, confidence(0-100)}`
- 用较便宜模型（`DEFAULT_LLM_MODEL` 倾向 haiku/gpt-4o-mini，由 `SUPPLY_CHAIN_DISCOVER_MODEL` 覆盖）
- 结果按 ticker + 日期缓存（Redis，TTL 见 §8）

### 5.2 resolve —— 名称规范化 + 映射 ticker + upsert
`resolve_suppliers(ticker, suppliers, session) -> GiraffeGraph`
- 供应商名规范化（复用 `app/services/graph/normalizer.py:normalize_entity_name`）
- 经「全市场股票池」匹配 ticker：新增 `app/services/supply_chain/fmp_universe.py`
  - 启动时拉取 FMP `/stock/list`（仅美股交易所 NYSE/NASDAQ/AMEX），按 symbol 大写 + name 建本地索引，缓存在 Redis（24h TTL）
  - 名称→ticker 匹配：精确名 → 别名 → 模糊（token 重叠）；命中则 `node_id=ticker`、`is_listed=True`、`resolved=True`；未命中则 `node_id=uuid(canonical_name)`、`is_listed=False`
- 组装为 `GiraffeEdge`（`supplier → company`, `edge_type=SUPPLIED_BY`, `properties.product/confidence/confidence_source=LLM/rationale`）+ `GiraffeNode`
- repository `upsert_graph(graph, run_id)`：按 `edge_id`/`node_id` 幂等写入（重跑更新 confidence/properties，不新增）

### 5.3 filter —— 选低分关系
`select_low_confidence_edges(ticker, threshold=60) -> list[GiraffeEdge]`
- 查 `SupplyChainEdge` where `dst_node_id=ticker` and `confidence < threshold` and `confidence_source = LLM`
- 装回 `GiraffeEdge`（含两端节点 properties）

### 5.4 verify —— SEC 文件分析 + 带立场线索 + 重打分
`verify_with_sec(edges: list[GiraffeEdge], llm) -> None`
- 对每条低分 edge：
  1. 抓 buyer（= dst 公司）最新 10-K（复用 `app/services/graph/sec_fetcher.py:sec_fetcher.fetch_latest_filing_text(ticker, form_type="10-K", section_hint=...)`），section 聚焦 Business / Risk Factors / MD&A 中的供应链、原材料、商品、单一来源供应商段落；10-K 拿不到兜底 10-Q
  2. 把 edge + buyer 节点 + 供应商名装成小 `GiraffeGraph`，用 `GiraffeGraph.trim_to_token_limit` 裁剪到模型上限
  3. 强模型（`SUPPLY_CHAIN_VERIFY_MODEL`，倾向 sonnet/gpt-4o）抽取**带立场线索**：`[{snippet, stance, section, confidence_delta}]`
  4. 落 `SupplyChainClue`（`edge_id` 必挂；`stance`/`source_type=SEC_10K`/`document_url`/`section`/`filing_date`/`snippet_text`/`confidence_delta`）；关键实体（被点名的新供应商）也建/挂 `node_id`
  5. 同模型综合所有线索**重新给 0-100 分**，更新 `edge.confidence` + `confidence_source=SEC_VERIFIED` + `evidence_summary`；**只加线索、不删关系**（被反驳也只降分）
- 限流：SEC ≤10 req/s（`sec_fetcher` 已含 UA/限速），FMP 按套餐配置

### 5.5 单公司编排
`run_company_pipeline(ticker, run_id, llm)`：DISCOVER → RESOLVE → SEC_VERIFY 顺序执行，逐阶段更新 `SupplyChainTask`，异常向上抛由 Celery 重试。

## 6. Celery 任务队列 + 任务管理

### 6.1 Celery 实例
`app/core/celery_app.py`：
- `Celery("deepalpha", broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)`，broker/backend 均用 Upstash Redis（`VALKEY_*` 拼接，`CELERY_SSL=true`）
- `autodiscover_tasks(["app.tasks"])`
- `task_serializer="json"`、`result_serializer="json"`、`timezone="UTC"`
- 配置 worker 并发（`SUPPLY_CHAIN_WORKER_CONCURRENCY`，默认 4）、`task_default_rate_limit`（默认 `30/m`，约束整体节奏）

### 6.2 任务（`app/tasks/supply_chain.py`）
- `run_supply_chain_batch(run_id)`：
  - 按 `universe` 枚举股票池（从 `fmp_universe` 取，按 universe 过滤）
  - 为每个 ticker 建 `SupplyChainTask(stage=DISCOVER, status=queued)` 并 `process_company.delay(run_id, ticker)`
  - 更新 `SupplyChainRun.total`
- `process_company(run_id, ticker)`：
  - `autoretry_for=(Exception,)`、`retry_backoff=True`、`retry_backoff_max=600`、`retry_jitter=True`、`max_retries=3`
  - 内部用 `get_sync_session()`（符合 CLAUDE.md 约定）
  - 调 `run_company_pipeline(ticker, run_id, llm_registry.get_default())`
  - 逐阶段更新 task 状态；成功写 `result_summary`，失败写 `error` 并置 `retrying`/`failed`
  - 完成后更新 run 的 `completed`/`failed` 计数，全部完成置 `done`
- Celery 任务内 LLM/FMP 异步调用用 `asyncio.run(...)` 包装（这些 client 是 async）

### 6.3 限流与并发
- Celery `rate_limit` 约束整体；`asyncio.Semaphore` 约束单任务内并发
- 跳过近期已跑公司：run 启动时按 `SupplyChainTask.updated_at > now - N days and status=success` 过滤（`SUPPLY_CHAIN_SKIP_RECENT_DAYS`，默认 7）

### 6.4 可选 beat
`app/core/celery_app.py` 配 beat schedule：每日增量刷新一部分低置信度关系（`SUPPLY_CHAIN_BEAT_ENABLED` 默认 false，先不开）。

### 6.5 部署
`Procfile` 新增：
```
worker: /app/.venv/bin/celery -A app.core.celery_app worker --loglevel=info -Q supply_chain
beat: /app/.venv/bin/celery -A app.core.celery_app beat --loglevel=info
```
Railway 新增 worker 服务（与 web 共享镜像，启动命令不同）。

## 7. API + 前端

### 7.1 后端路由（`app/api/v1/supply_chain_map.py`，前缀 `/supply-graph`）
> 与现有 `/supply-chain`（FinReflect 图谱）区分，避免冲突。在 `api.py` 注册。
- `POST /supply-graph/companies/{ticker}/run` —— 单公司按需（创建 single run，触发 `process_company.delay`）
- `POST /supply-graph/runs` —— body `{universe}` 触发 batch run
- `GET /supply-graph/runs` / `GET /runs/{run_id}` —— 运行列表/详情（含 task 列表与进度）
- `POST /runs/{run_id}/pause` / `/resume` / `/retry-failed` —— 控制（pause=撤回队列中任务，retry-failed=重投 failed 任务）
- `GET /supply-graph/graph?ticker=&depth=` —— 取节点+边（`GiraffeGraph.to_dict()` 输出 camelCase，便于前端）
- `GET /supply-graph/edges/{edge_id}/clues` —— 取该关系的线索列表

遵循分层规则：路由只做参数解析 + 调 service；service 在 `app/services/supply_chain/`。

### 7.2 前端（Next.js，`TopNav` 注册）
- `/supply-graph`：图谱可视化（节点=公司/供应商，边按 `confidence` 分档配色：<60 黄、60-79 蓝、≥80 绿），点边 → 右侧线索面板（原文片段、`stance` 标签、SEC 来源链接、`filing_date`）。图表库沿用项目现有 lightweight-charts 或引入轻量关系图组件（实现期决定，倾向用 react-force-graph 或自绘 SVG）
- `/supply-graph/tasks`：任务看板——runs 列表（状态/进度条/完成数）+ 选中 run 的 task 表（ticker/stage/status/retries/error），支持暂停/续跑/重试失败
- `frontend/lib/api/supplyGraph.ts`（Axios 封装，统一 `lib/api/client.ts`）

## 8. 配置（`app/core/config.py` + `.env.example`）

```
# Celery
CELERY_BROKER_URL=redis://...        # 默认复用 VALKEY_* 拼接
CELERY_RESULT_BACKEND=redis://...
CELERY_SSL=true
SUPPLY_CHAIN_WORKER_CONCURRENCY=4

# 供应链图谱
SUPPLY_CHAIN_UNIVERSE=sp500          # 默认 mvp 范围
SUPPLY_CHAIN_LOW_CONFIDENCE_THRESHOLD=60
SUPPLY_CHAIN_SKIP_RECENT_DAYS=7
SUPPLY_CHAIN_DISCOVER_MODEL=         # 空=用 DEFAULT_LLM_MODEL
SUPPLY_CHAIN_VERIFY_MODEL=           # 空=用 DEFAULT_LLM_MODEL
SUPPLY_CHAIN_BEAT_ENABLED=false
SUPPLY_CHAIN_DISCOVER_CACHE_TTL=86400
```

## 9. 分阶段上线与成本

1. **阶段 1（MVP）**：`SUPPLY_CHAIN_UNIVERSE=sp500`，跑通单公司按需 + batch，验证供应商抽取质量与 SEC 验证效果，估算单公司成本（LLM 调用数 + token + SEC 请求数）。
2. **阶段 2**：放量到 `nasdaq100` 合并去重，再 `russell1000`。
3. **阶段 3**：`full`（~6000），开启 beat 增量刷新。
- 成本控制：discover 结果按 ticker+日期缓存；跳过近期已跑公司；discover 用便宜模型、verify 仅对 <60 分关系触发（多数关系不会进入 verify）。
- 6000 家 × Top 5-10 供应商，预估 discover LLM 调用 ~6000 次；verify 仅作用于 <60 分子集（按经验 20-40%），SEC 抓取 ~1200-2400 次，可承受。

## 10. 测试（TDD，`tests/services/supply_chain/`）

`asyncio_mode=auto`，LLM/FMP/SEC 全 mock，`@pytest.mark.slow` 标真实外呼。
- `test_fmp_universe.py`：名称→ticker 匹配（精确/别名/模糊/未命中）
- `test_resolver.py`：规范化去重、ticker 映射、命名实体回退
- `test_discover.py`：LLM 结构化返回解析、Top-N 截断、confidence 范围
- `test_verify.py`：带立场线索抽取、线索落库、综合重打分、只加不删
- `test_repository.py`：↔GiraffeGraph 映射、`edge_id` 幂等 upsert
- `test_giraffe_graph.py`：摘取后的领域对象核心算法（sub_graph/trim_to_token_limit/to_dict）回归
- `test_pipeline.py`：单公司 4 步端到端（mock 全外部依赖）
- `test_tasks.py`：task 状态机流转、重试、run 计数
- 前端：`cd frontend && npx tsc --noEmit` 通过

## 11. 落地清单（每完成一小步即提交）

1. 摘取 `giraffe_graph.py` 到 `app/services/supply_chain/domain/`，替换依赖（+ `uv add networkx pandas`）
2. 五张 SQLModel 表 + alembic 迁移
3. `fmp_universe.py` 全市场股票池 + 名称→ticker 匹配（含测试）
4. `repository.py` ↔GiraffeGraph 映射 + upsert（含测试）
5. `discover.py`（含测试）
6. `resolve.py`（含测试）
7. `verify.py`（含测试）
8. `pipeline.py` 单公司编排（含测试）
9. `app/core/celery_app.py` + `app/tasks/supply_chain.py`（含测试）
10. 后端路由 `/supply-graph`（含测试）
11. 配置项 + `.env.example`
12. 前端图谱页 + 任务看板页 + `lib/api/supplyGraph.ts`
13. `Procfile` worker/beat + 文档（README 补充启动方式）
14. `make check`（ruff + pyright）+ 前端 `tsc --noEmit` 通过

## 12. 不在本期范围（YAGNI）

- 图数据库（Neo4j/AGE）持久化——当前规模 SQLModel + JSON 属性足够
- 全市场一次性同步跑完——分阶段 + beat 增量
- 供应商财务健康度评分、替代供应商推荐——未来扩展
- 与现有 `/supply-chain` FinReflect 图谱合并——保持解耦