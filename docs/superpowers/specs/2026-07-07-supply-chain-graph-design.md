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
| 前端图谱 | **AntV G6 v6**（`@antv/g6@^6`），关系图谱专用引擎；单公司中心 + 可漫游焦点模式 |

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
- `status: str`（`pending`/`running`/`paused`/`paused_quota`/`done`/`failed`，索引）—— `paused` 手动暂停，`paused_quota` 配额耗尽自动暂停
- `total: int`、`completed: int`、`failed: int`
- `params: JSON`（universe 过滤、模型名、阈值等）
- `quota_paused_at: datetime | None`、`resume_after: datetime | None`（配额恢复预估时间，见 §7）
- `probe_attempts: int`（额度探测次数，封顶防无限探测）
- `started_at`、`finished_at`、`created_at`

**`SupplyChainTask`**（`app/models/supply_chain_task.py`）—— 单公司任务
- `run_id: UUID`（外键，索引）
- `ticker: str`（索引）
- `stage: str`（`DISCOVER`/`RESOLVE`/`SEC_VERIFY`，当前阶段）
- `status: str`（`queued`/`running`/`success`/`failed`/`retrying`/`paused_quota`，索引）—— `paused_quota` 表示因配额耗尽被延迟重投
- `retries: int`、`max_retries: int`
- `quota_retries: int`（配额恢复重投次数，独立计数，不占普通 `retries` 配额）
- `celery_task_id: str | None`
- `error: str | None`
- `resume_after: datetime | None`（该任务延迟重投的预计恢复时间）
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
- 结果按 ticker + 日期缓存（Redis，TTL 见 §9）

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

## 7. 稳定性与限流恢复（MiniMax 5 小时窗口）

> 现有 `llm_service` 的 tenacity 指数退避（2-10s）+ 多模型循环 fallback 针对的是「单次调用瞬时失败」。本节处理另一量级问题：**长时窗配额耗尽（如 MiniMax 5 小时上限）+ 额度恢复后自动续跑**。两层不能混在一起——对 5 小时窗口做 10s 退避重试 3 次必然失败、还会白白耗尽重试配额把任务误标 failed。

### 7.1 LLM 调用层：区分「瞬时限流」与「额度耗尽」

在 `llm_service` 捕获 `RateLimitError` 时解析错误体，区分两种情况：

- **瞬时限流**（窗口秒级滚动）：保留现有指数退避重试（`_invoke_with_retry`）
- **额度耗尽**（5 小时长窗口）：**不退避重试**，抛新异常 `LLMQuotaExhausted(provider, retry_after_hint)`，交由 Celery 任务层处理「延迟重投」而非「立即失败」

判定逻辑：
- 优先用 MiniMax 响应里的 `retry_after` / 限流类型字段（按 MiniMax 错误码与响应体解析）
- 兜底用错误消息关键词（"quota"/"5 小时"/"rate limit window" 等）+ 配置的固定窗口 `SUPPLY_CHAIN_QUOTA_WINDOW_SECONDS`（默认 18000=5h）
- 解析不出则保守按「额度耗尽」处理（宁可多等，不要误判成瞬时把任务标 failed）

> 改动范围：`app/services/llm/service.py` 新增 `LLMQuotaExhausted` 异常 + 在 `_invoke_with_retry` / `_fallback_loop` 里识别。这是对现有 LLM 服务的**通用增强**，其他模块也受益。

### 7.2 任务层：限流感知的延迟重投

`process_company` 的重试策略分两路：

- **普通异常**（网络/超时/瞬时限流或其他非配额错误）：`autoretry_for`，指数退避，`max_retries` 用普通配额（保持现有 3 次）
- **`LLMQuotaExhausted`**：走**专门的延迟重投路径**：
  1. 当前 task 置 `status=paused_quota` + `resume_after = now + 预估恢复时间`，`quota_retries += 1`
  2. 不计普通 `retries` 配额（额度等待不是「出错」）
  3. 用 `process_company.apply_async(args=[run_id, ticker], countdown=resume_after - now)` 延迟重投——countdown 可达数小时
  4. `quota_retries` 上限 `SUPPLY_CHAIN_MAX_QUOTA_RETRIES`（默认 10，封顶防卡死）

### 7.3 批次层：额度恢复后的自动续跑（核心）

`SupplyChainRun` 在配额耗尽时进入 `paused_quota` 状态，并由**延迟续跑任务**在额度恢复窗口到期后自动恢复整批：

1. `process_company` 第一次抛 `LLMQuotaExhausted` 时：
   - 置 run `status=paused_quota`、`quota_paused_at=now`、`resume_after` 取所有受影响 task 的最早恢复时间
   - 投延迟任务 `resume_run_if_quota_recovered.apply_async(args=[run_id], countdown=resume_after - now)`
   - 暂停 `run_supply_chain_batch` 对剩余 ticker 的 `delay` 派发（避免继续撞限流）
2. `resume_run_if_quota_recovered(run_id)` 在延迟后执行：
   - 先发**探测调用**（极小 token，如单字 "ping"）验证 MiniMax 是否真有额度
   - **有额度** → 置 run `running`、`probe_attempts=0`，重新 `delay` 所有 `paused_quota` 的 task 与剩余 queued ticker，**续跑**
   - **仍未恢复** → `probe_attempts += 1`，再延迟一个探测窗口（指数退避：1 min → 5 min → 15 min，封顶 `SUPPLY_CHAIN_MAX_PROBE_ATTEMPTS=10`），避免无限探测；超过上限则置 run `failed` 并记录原因（需人工介入）

这样即使配额在凌晨 3 点恢复，系统也会自动续跑，无需人工介入。

### 7.4 任务管理 API 对接

`/runs/{run_id}/resume` 手动恢复接口也复用 `resume_run_if_quota_recovered` 的逻辑（强制探测+续跑）。前端任务看板对 `paused_quota` 状态显示「⏸ 配额等待中，预计 HH:MM 恢复」徽标 + 剩余恢复倒计时，并允许「立即重试」。

### 7.5 章节小结：稳定性策略

| 故障类型 | 处理 | 重试上限 |
|---------|------|---------|
| 网络超时 / 瞬时 429 | tenacity 指数退避（现有） | `MAX_LLM_CALL_RETRIES=3`（单次调用）|
| 单模型失败 | 多模型循环 fallback（现有） | registry 长度 |
| 配额耗尽（5h 窗口） | task `paused_quota` + Celery `countdown` 延迟重投 | `SUPPLY_CHAIN_MAX_QUOTA_RETRIES=10`（按 task）|
| 额度恢复续跑 | `resume_run_if_quota_recovered` 探测 + 整批恢复 | `SUPPLY_CHAIN_MAX_PROBE_ATTEMPTS=10` |
| 完全失败 | 标 `failed`，前端可 `retry-failed` 重投 | — |

## 8. API + 前端

### 8.1 后端路由（`app/api/v1/supply_chain_map.py`，前缀 `/supply-graph`）
> 与现有 `/supply-chain`（FinReflect 图谱）区分，避免冲突。在 `api.py` 注册。
- `POST /supply-graph/companies/{ticker}/run` —— 单公司按需（创建 single run，触发 `process_company.delay`）
- `POST /supply-graph/runs` —— body `{universe}` 触发 batch run
- `GET /supply-graph/runs` / `GET /runs/{run_id}` —— 运行列表/详情（含 task 列表与进度）
- `POST /runs/{run_id}/pause` / `/resume` / `/retry-failed` —— 控制（pause=撤回队列中任务，retry-failed=重投 failed 任务）
- `GET /supply-graph/graph?ticker=&depth=1` —— 取以 `ticker` 为中心、`depth` 度邻域的子图（后端用 `GiraffeGraph.sub_graph(seed_nodes=[company])` 裁剪后 `to_dict()` 输出 camelCase，含 nodes/edges/properties）
- `GET /supply-graph/graph/expand?from_node_id=&depth=1` —— 漫游：以当前某节点为新焦点增量拉取邻域，前端 merge 进已有图
- `GET /supply-graph/edges/{edge_id}/clues` —— 取该关系的线索列表（按 `stance`/`filing_date` 排序）
- `GET /supply-graph/nodes/{node_id}/detail` —— 节点详情（公司画像 + 入度/出度 + 关键供应关系摘要）

遵循分层规则：路由只做参数解析 + 调 service；service 在 `app/services/supply_chain/`。

### 8.2 前端（Next.js，`TopNav` 注册）

**技术选型**：采用 **AntV G6 v6**（`@antv/g6@^6`）。G6 是专为关系图谱设计的图分析引擎（区别于 xyflow 的「节点画布」定位），内置力导/层次/辐射/dagre 等多种布局、WebGL 高性能渲染、节点聚合/过滤/图分析算法，更适合供应链图谱「单公司中心 + 可漫游 + 节点边可能上千」的探索体验。现有 `/supply-chain` 页的 `@xyflow/react` 组件保持不变，新页面独立用 G6，两套不互相干扰。

> ⚠️ **实施首步必须验证兼容性**：G6 v6（2025 年发布）与 React 19 + Next.js 16 的集成需先跑通一个最小 demo（SSR 关闭、`'use client'`、动态 import）再铺开。本项目 Next.js 版本较新，前端编码前先查 `frontend/node_modules/next/dist/docs/`（见 `frontend/AGENTS.md`）。若 G6 v6 兼容性阻断，回退到 `@antv/g6@^5`。实施阶段涉及视觉细节时用 frontend-design skill 打磨。

**焦点模式：单公司中心 + 可漫游**
- 默认以某家公司为种子展示其供应商图谱（`depth=1`，即直接上游供应商）；单次数据量小、加载快、贴合「查这家公司供应链」的直觉
- 双击节点 → 以该节点为新焦点 `expand`，前端按 G6 的 graph data 增量合并（按 `node_id`/`edge_id` 去重）+ `fitView` 聚焦
- 顶部搜索框：输入 ticker/公司名定位并切换焦点公司

**G6 集成要点**：
- G6 实例仅在客户端创建（Next 16 SSR 下用 `dynamic(() => import(...), { ssr: false })` 或 `useEffect` 内挂载）
- 数据契约对齐 §3 的 `GiraffeGraph.to_dict()`（camelCase：nodes `{id,type,properties}` / edges `{source,target,type,timestamp,properties}`）——后端直接输出该格式，前端 G6 的 `graph.setData()` 直接消费
- 布局：单公司中心用 **radial（辐射）布局**（焦点公司在中心，供应商放射展开）；漫游切换到 **force（力导）布局** 适合多度子图
- 节点/边样式用 G6 的 maping（按 `properties.confidence`/`properties.type` 映射颜色与粗细）

**新建组件** `frontend/components/supply_graph/`：
- `SupplyGraphCanvas.tsx`（G6 图实例管理：挂载/卸载、布局切换、zoom/pan、fitView）
- `SupplyGraphAdapter.tsx`（数据契约适配 + 漫游合并逻辑，封装 API 调用与 G6 data 转换）
- `EdgeClueDrawer.tsx`（边点击 → 右侧抽屉）
- `NodeDetailPanel.tsx`（节点点击 → 详情面板）
- `GraphFilters.tsx`（置信度阈值滑块、universe 过滤、来源筛选）
- `RoamerBreadcrumb.tsx`（漫游路径面包屑，支持回退到上一个焦点）

**UX 增强清单**（实施阶段用 frontend-design skill 打磨视觉）：
- **节点**：节点大小按「被依赖度」（入度，作为多少家公司的供应商）映射，凸显关键供应商；节点配色按类型（company/supplier）；hover 显示 name/ticker/aliases/description 气泡
- **边**：粗细与颜色按 `confidence` 分档（<60 黄虚线动画、60-79 蓝、≥80 绿粗实线）；边 label 显示 `product`；hover tooltip 显示 `evidence_summary` + `confidence_source` 徽标（LLM/SEC_VERIFIED）
- **线索抽屉**：点击边 → 右侧抽屉列出 `SupplyChainClue`，每条带 `stance` 色标（SUPPORT 绿/REFUTE 红/NEUTRAL 灰）、原文 `snippet_text`、SEC `document_url` 跳转、`filing_date`、`section`、`confidence_delta`
- **过滤**：置信度阈值滑块（实时过滤边，G6 的 `filter` API）、按 `confidence_source` 筛选（只看 SEC 验证过的）、搜索高亮节点
- **导航**：G6 内置 Minimap 插件 + ToolBar 插件（缩放/居中/锁定）；面包屑记录漫游路径（A → B → C），可回退
- **状态反馈**：单公司按需 run 时，图谱区显示该 ticker 的 task 进度（DISCOVER→RESOLVE→SEC_VERIFY 阶段条 + 完成后自动刷新图谱）；轮询或 SSE 推送进度

**任务看板页** `/supply-graph/tasks`（G6 之外，用 shadcn/ui 表格）：
- runs 列表（状态徽标 / 进度条 / completed-failed 计数 / 起止时间）
- 选中 run → 展开该 run 的 task 表（ticker / stage / status / retries / error），失败行可展开看 error 详情
- 操作按钮：暂停（撤回 queued 任务）/ 续跑 / 重试失败 / 删除 run
- `frontend/lib/api/supplyGraph.ts`（Axios 封装，统一 `lib/api/client.ts`）

## 9. 配置（`app/core/config.py` + `.env.example`）

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

# 限流与配额恢复（见 §7）
SUPPLY_CHAIN_QUOTA_WINDOW_SECONDS=18000   # 5h，MiniMax 窗口兜底
SUPPLY_CHAIN_MAX_QUOTA_RETRIES=10         # 单 task 配额重投上限
SUPPLY_CHAIN_MAX_PROBE_ATTEMPTS=10        # 额度探测上限
SUPPLY_CHAIN_PROBE_BACKOFF_SECONDS=60     # 探测退避起始（60→300→900 封顶）
```

## 10. 分阶段上线与成本

1. **阶段 1（MVP）**：`SUPPLY_CHAIN_UNIVERSE=sp500`，跑通单公司按需 + batch，验证供应商抽取质量与 SEC 验证效果，估算单公司成本（LLM 调用数 + token + SEC 请求数）。
2. **阶段 2**：放量到 `nasdaq100` 合并去重，再 `russell1000`。
3. **阶段 3**：`full`（~6000），开启 beat 增量刷新。
- 成本控制：discover 结果按 ticker+日期缓存；跳过近期已跑公司；discover 用便宜模型、verify 仅对 <60 分关系触发（多数关系不会进入 verify）。
- 6000 家 × Top 5-10 供应商，预估 discover LLM 调用 ~6000 次；verify 仅作用于 <60 分子集（按经验 20-40%），SEC 抓取 ~1200-2400 次，可承受。

## 11. 测试（TDD，`tests/services/supply_chain/`）

`asyncio_mode=auto`，LLM/FMP/SEC 全 mock，`@pytest.mark.slow` 标真实外呼。
- `test_fmp_universe.py`：名称→ticker 匹配（精确/别名/模糊/未命中）
- `test_resolver.py`：规范化去重、ticker 映射、命名实体回退
- `test_discover.py`：LLM 结构化返回解析、Top-N 截断、confidence 范围
- `test_verify.py`：带立场线索抽取、线索落库、综合重打分、只加不删
- `test_repository.py`：↔GiraffeGraph 映射、`edge_id` 幂等 upsert
- `test_giraffe_graph.py`：摘取后的领域对象核心算法（sub_graph/trim_to_token_limit/to_dict）回归
- `test_pipeline.py`：单公司 4 步端到端（mock 全外部依赖）
- `test_tasks.py`：task 状态机流转、重试、run 计数
- `test_quota_recovery.py`：`LLMQuotaExhausted` 识别、task `paused_quota` 延迟重投、`resume_run_if_quota_recovered` 探测成功/失败两条路径、探测退避封顶、`probe_attempts` 超限置 failed
- 前端：`cd frontend && npx tsc --noEmit` 通过（含 G6 v6 与 React 19/Next 16 集成类型检查）

## 12. 落地清单（每完成一小步即提交）

1. 摘取 `giraffe_graph.py` 到 `app/services/supply_chain/domain/`，替换依赖（+ `uv add networkx pandas`）
2. 五张 SQLModel 表 + alembic 迁移
3. `fmp_universe.py` 全市场股票池 + 名称→ticker 匹配（含测试）
4. `repository.py` ↔GiraffeGraph 映射 + upsert（含测试）
5. `discover.py`（含测试）
6. `resolve.py`（含测试）
7. `verify.py`（含测试）
8. `pipeline.py` 单公司编排（含测试）
9. `app/core/celery_app.py` + `app/tasks/supply_chain.py`（含测试）
9b. `llm_service` 新增 `LLMQuotaExhausted` + 限流识别；`process_company` 配额延迟重投；`resume_run_if_quota_recovered` 探测续跑（含 `test_quota_recovery.py`）
10. 后端路由 `/supply-graph`（含测试）
11. 配置项 + `.env.example`
12. 前端：**先验证 G6 v6 与 React 19/Next 16 最小集成**（`'use client'` + 动态 import + SSR 关闭 demo），通过后再铺开；若阻断回退 `@antv/g6@^5`
13. 前端图谱页（G6 canvas + 漫游 + 线索抽屉 + 过滤） + 任务看板页（shadcn 表格） + `lib/api/supplyGraph.ts`
14. `Procfile` worker/beat + 文档（README 补充启动方式）
15. `make check`（ruff + pyright）+ 前端 `tsc --noEmit` 通过

## 13. 不在本期范围（YAGNI）

- 图数据库（Neo4j/AGE）持久化——当前规模 SQLModel + JSON 属性足够
- 全市场一次性同步跑完——分阶段 + beat 增量
- 供应商财务健康度评分、替代供应商推荐——未来扩展
- 与现有 `/supply-chain` FinReflect 图谱合并——保持解耦