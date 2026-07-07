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
- ⚠️ **必须改造资金专用常量**：原 `GiraffeGraph.KEY_PROPERTIES = {is_core, gmt_occur, amt, goods_title, operation_channel, biz_scene, biz_prod_code}` 与 `_trim_non_core_connected`(按 `is_core`)、`fifo`(资金时序裁剪) 都是**金融风控专用**，直接移植会把供应链的 `product/confidence/product_category` 等字段裁光。摘取时：
  - `KEY_PROPERTIES` 替换为供应链白名单 `{confidence, confidence_source, product, product_category, is_single_source, ticker, is_listed, expandable}`
  - 删除 `fifo`（资金时序专用，无意义）与 `_trim_non_core_connected` 里的 `is_core` 语义
  - `trim_to_token_limit` 的度数裁剪逻辑保留，但裁剪优先级改为「按 confidence 升序裁剪」（低置信度先丢）

> 图谱语义约定（本子系统内）：
> - `node_type` ∈ `{"company", "supplier"}`（company = 上市采购方；supplier = 上游供应方，已映射 ticker 的 supplier 仍用 "supplier" 类型，但 `properties.ticker` 标明可交易标的）
> - `edge_type` ∈ `{"SUPPLIED_BY"(supplier→company), "CUSTOMER_OF"(company→customer)}`——discover 同时问上游供应商与下游客户（见 §5.1），补全下游关系
> - `timestamp` = 关系抽取/最近一次验证的秒级时间戳
> - 边 `properties`：`product`(自由文本)、`product_category`(归一类目ID)、`confidence`(0-100 int)、`confidence_source`(`LLM`/`SEC_VERIFIED`/`MULTI_SOURCE_VERIFIED`/`UNVERIFIED`)、`status`(`active`)、`rationale`、`evidence_summary`、`is_single_source`(bool)、`changed`(bool,重跑变化标记)
> - 节点 `properties`：`name`(规范名)、`ticker`、`aliases`、`resolved`(bool)、`is_listed`(bool)、`expandable`(bool,私有/境外节点不可追溯上游)、`description`

## 4. 数据模型（SQLModel，新建，继承 `UUIDModel`）

> 字段语义对齐 `GiraffeNode/GiraffeEdge`，使 repository 层映射为薄层。`properties` 用 JSON 列承载 `GiraffeProperty` 列表。

### 4.1 图谱三表

**`SupplyChainNode`**（`app/models/supply_chain_node.py`）
- `node_id: str`（业务主键，索引唯一）：能映射 ticker 的用 ticker 大写（如 `TSM`），否则用规范名称的确定性 UUID（`generate_uuid_from_str(canonical_name)`）
- `node_type: str`（`company` / `supplier`）
- `name: str`（规范主名称，索引）
- `properties: JSON`（承载 GiraffeProperty 列表：ticker/aliases/resolved/is_listed/expandable/description）—— `expandable` 标记私有/境外节点不可继续追溯上游（硬伤 3）
- `first_seen_run_id: UUID | None`、`updated_at`
- 去重：按 `node_id` 唯一（ticker 优先）

**`SupplyChainEdge`**（`app/models/supply_chain_edge.py`）
- `edge_id: str`（确定性，索引唯一）：基于 `(src_id,dst_id,edge_type,product_category 归一键)` 生成——**不含 timestamp**（timestamp 会随 verify 更新变值，会导致 upsert 误建新边）。幂等键，重跑 verify 更新而非新增。`GiraffeEdge.generate_edge_id` 原实现含 timestamp，摘取时改为不含
- `src_node_id: str`、`src_type: str`、`dst_node_id: str`、`dst_type: str`、`edge_type: str`（`SUPPLIED_BY` / `CUSTOMER_OF`）
- `timestamp: int`（秒级）
- `properties: JSON`（product/product_category/confidence_source/status/rationale/evidence_summary/is_single_source/changed）
- `confidence: int`（0-100，冗余字段便于按阈值查询与索引）
- `confidence_source: str`（`LLM`/`SEC_VERIFIED`/`MULTI_SOURCE_VERIFIED`/`UNVERIFIED`，索引）—— `UNVERIFIED` 表示 verify 后零证据、仅 LLM 猜测
- `last_run_id: UUID | None`、`updated_at`
- 索引：`(dst_node_id)`（按采购方查其供应商）、`(src_node_id)`（按供应商查其客户 / 多度 BFS 双向，见 §8.3）、`confidence`、`confidence_source`、`edge_type`

**`SupplyChainClue`**（`app/models/supply_chain_clue.py`）—— 线索（带立场证据片段 / 变化标记）
- `edge_id: str | None`（挂到某条关系；索引）
- `node_id: str | None`（同时挂到关键实体）
- `source_type: str`（`EARNINGS_CALL`/`NEWS`/`SEC_10K`/`SEC_10Q`/`SEC_8K`/`DIFF`，索引）—— `DIFF` 表示重跑变化检测产出的线索（硬伤时效性）
- `document_url: str`、`section: str | None`、`filing_date: date | None`
- `snippet_text: str`（原文片段）
- `stance: str`（`SUPPORT`/`REFUTE`/`NEUTRAL`/`CHANGED`，索引）—— `CHANGED` 用于变化检测
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
- `stage: str`（`DISCOVER`/`RESOLVE`/`EVIDENCE_VERIFY`，当前阶段）
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

### 5.1 discover —— 问供应商 + 产品 + 模型置信度（含 unknown 与下游客户）
`discover_suppliers(ticker: str, llm) -> dict`
- 一次结构化 LLM 调用，返回：
  - `suppliers`：Top 5-10 上游供应商 `{supplier_name, product_text, rationale, confidence(0-100), is_single_source(bool), info_year(知识来源年份|None)}`（`product_category` 不由 LLM 给，统一在 §5.2 resolve 阶段用 `product_taxonomy` 归一，避免 LLM 不可靠于返回固定枚举 ID）
  - `customers`：Top 5-10 核心客户 `{customer_name, product_text, confidence, info_year}`（**边际零成本**，同一次调用顺便问，补下游关系——见硬伤 4 缓解）
  - `skipped: bool` + `skip_reason`：LLM 对该公司**无足够知识**时返回 skipped，不硬填（见硬伤 2 缓解）
- prompt 强制要求：信息不足时必须返回 `skipped=true`，禁止编造；`confidence` 反映「模型对自己这条事实有多确定」而非「关系强弱」
- 用较便宜模型（`DEFAULT_LLM_MODEL` 倾向 haiku/gpt-4o-mini，由 `SUPPLY_CHAIN_DISCOVER_MODEL` 覆盖）
- 结果按 ticker + 日期缓存（Redis，TTL 见 §9）
- 写入时：`skipped=true` 的 task 直接置 `success`（`result_summary={skipped:true}`），不建边，**避免用 LLM 猜测污染图谱**

### 5.2 resolve —— 名称规范化 + 映射 ticker + upsert + 产品归一
`resolve_suppliers(ticker, suppliers, session) -> GiraffeGraph`
- 供应商名规范化（复用 `app/services/graph/normalizer.py:normalize_entity_name`）
- **别名归一**（硬伤 5）：私有/境外供应商同一实体多名（Foxconn/富士康/Hon Hai）。新增 `app/services/supply_chain/alias_resolver.py`：维护一张别名表（种子 + LLM 一次性归一扩展），归一后再取 `node_id`，避免重复节点破坏连通性
- 经「全市场股票池」匹配 ticker：新增 `app/services/supply_chain/fmp_universe.py`
  - 启动时拉取 FMP `/stock/list`（仅美股交易所 NYSE/NASDAQ/AMEX），按 symbol 大写 + name 建本地索引，缓存在 Redis（24h TTL）
  - 名称→ticker 匹配：精确名 → 别名 → 模糊（token 重叠）；命中则 `node_id=ticker`、`is_listed=True`、`resolved=True`；未命中则 `node_id=uuid(canonical_name)`、`is_listed=False`
  - **断链标记**（硬伤 3）：未上市/境外/私有节点置 `expandable=false`，前端用特殊样式表明「此处为知识边界，无法继续追溯上游」
  - **市值落库（#5）**：buyer 公司经 FMP profile 拉取 `marketCap` 存入 `node.properties.market_cap`（缓存 24h），供 §5.3 filter 判断中小盘；supplier 若上市同样落 `market_cap`
- **产品类目归一**（硬伤 5）：`product_text` 自由文本归一到轻量本体类目 ID（种子几十类：芯片代工/HBM/光刻设备/封装测试/稀土/化学品…，存在 `app/services/supply_chain/product_taxonomy.py`），写入 `edge.properties.product_category`，使「某类产品被谁垄断」可聚合分析
- 组装为 `GiraffeEdge`（`supplier → company`, `edge_type=SUPPLIED_BY`, `properties.product/product_category/confidence/confidence_source=LLM/rationale/is_single_source`）+ `GiraffeNode`（含 `expandable`）；`customers` 反向组装为 `CUSTOMER_OF` 边
- repository `upsert_graph(graph, run_id)`：按 `edge_id`/`node_id` 幂等写入（重跑更新 confidence/properties，不新增）

### 5.3 filter —— 选待验证关系（触发条件升级，硬伤 2 缓解）
`select_edges_to_verify(ticker, threshold=60) -> list[GiraffeEdge]`
- 旧条件 `confidence < 60` 在 LLM 系统性过度自信下基本不会触发，verify 形同虚设。升级为**任一命中即触发**：
  1. `confidence < SUPPLY_CHAIN_VERIFY_THRESHOLD`（默认 60）
  2. **或** supplier 命中「LLM 万能答案黑名单」（TSMC/Samsung/Intel/Google Cloud/AWS 等高频猜测，配置驱动）
  3. **或** buyer 属于中小盘（读 `node.properties.market_cap < SUPPLY_CHAIN_SMALLCAP_MARKETCAP`，对中小盘 LLM 知识差，强制 verify）
  4. **或** `is_single_source=true`（单一来源关系投资意义大，优先取证）
- 查 `SupplyChainEdge` where `dst_node_id=ticker` and `confidence_source = LLM` and (上述条件)，装回 `GiraffeEdge`（含两端节点 properties）
- 高置信度 + 大盘股 + 非单一来源的关系可跳过 verify（节省成本），但仍保留 `confidence_source=LLM` 标识未经验证

### 5.4 verify —— 多源级联取证 + 带立场线索 + 重打分（硬伤 1 缓解）
`verify_edges(edges: list[GiraffeEdge], llm) -> None`
- **证据源独立抓取**（各源并行/顺序抓取+独立落 clue，不「命中即止」——多源交叉才能 SUPPORT/REFUTE 互证）：
  1. **财报电话会**（命中率最高）：复用 `app/services/transcript_ai.py` + `app/services/graph/fmp_fetcher.fmp_transcript_fetcher`，取最近 4 个季度 transcript
  2. **8-K + 新闻稿**：复用 `app/services/analyzer/news_client`，按 `supplier_name + buyer ticker` 检索近 2 年新闻（签约/断供/扩产公告）
  3. **SEC 10-K**：复用 `sec_fetcher.fetch_latest_filing_text`，section 聚焦 Item 1 Business / Risk Factors / MD&A（10-K 多不点名供应商，但偶有大客户披露）
  4. **10-K Exhibit 21（子公司）+ 10-Q** 兜底
- **token 成本控制（#6）**：电话会/新闻/10-K 均**先按 supplier_name + buyer ticker 关键词检索（或 embedding）出相关片段**，只把片段（每源上限如 3 段 × 500 字）喂给强模型，**严禁整份 transcript/10-K 喂入**；片段为空则该源记 zero-evidence 不触发 LLM 调用
- 对每条 edge：把汇集的证据片段 + edge + buyer/supplier 节点装成小 `GiraffeGraph`，`trim_to_token_limit` 裁剪
- 强模型（`SUPPLY_CHAIN_VERIFY_MODEL`）抽取**带立场线索**：`[{snippet, stance, source_type, document_url, section, filing_date, confidence_delta}]`
- 落 `SupplyChainClue`（`edge_id` 必挂；`source_type` ∈ `EARNINGS_CALL/NEWS/SEC_10K/SEC_10Q/SEC_8K`；`stance` ∈ `SUPPORT/REFUTE/NEUTRAL`）；关键实体（被点名的新供应商）也建/挂 `node_id`
- 同模型综合所有线索**重新给 0-100 分**，更新 `edge.confidence` + `confidence_source`（`SEC_VERIFIED`/`MULTI_SOURCE_VERIFIED`）+ `evidence_summary`；**只加线索、不删关系**（被反驳也只降分）
- **零证据处理**：级联取证后若全部无提及，`confidence_source` 标 `UNVERIFIED`（区别于 `LLM`），不更新分数，前端用不同样式表明「LLM 猜测、无证据支持」——避免给用户「已验证」错觉
- 限流：SEC ≤10 req/s、FMP 按套餐、news 按套餐；各源独立限流 + 缓存（同 ticker 季度 transcript/新闻缓存复用）

### 5.5 单公司编排
`run_company_pipeline(ticker, run_id, llm)`：DISCOVER → RESOLVE → EVIDENCE_VERIFY 顺序执行，逐阶段更新 `SupplyChainTask`，异常向上抛由 Celery 重试。

### 5.6 质量保障：评估集 + 变化检测（硬伤 2/时效性缓解）

**小评估集（ground truth）**
- `evals/supply_chain/` 维护一份人工标注的已知供应链关系集（~50-100 条，含正例如 TSM→NVDA/ASML→TSM/Western Digital→Flash/Boeing→Spirit AeroSystems，与负例）
- 每次 discover/verify 跑完后，对评估集算 **precision / recall / 置信度校准曲线**（预测置信度 vs 实际正确率），用 `make eval` 触发
- **命中裁定规则（#13）**：预测边 `(supplier,buyer,product_category)` 与标注匹配时——supplier 经 `alias_resolver` 归一后等价（Foxconn=Hon Hai 算 hit）、buyer 按 ticker、product 按 `product_category` 等价（HBM=高带宽内存算 hit）；裁定脚本独立于被测代码，避免自我粉饰
- 校准差时（如高置信度区实际准确率 < 70%）输出告警，提示需要调 prompt 或阈值——让图谱质量**可量化、可回归**

**LLM 过度自信校正**
- discover prompt 里 `confidence` 语义明确为「事实确定性」并给校准示例（高=明确记忆/低=推测）；评估集校准曲线若整体偏高，对原始 confidence 施加**校准函数**（如分段线性压缩）后再入库

**变化检测（时效性）**
- 重跑某 ticker 时，与上次 edge 集做 `GiraffeGraph.diff`：新增/消失/置信度大幅变动的关系标记 `changed`，写入 `SupplyChainClue`（`source_type=DIFF`，支持前端高亮「本期变化」）
- beat 增量刷新聚焦「上次置信度低」「上次零证据」「近 N 天有新闻」的公司，而非无脑全刷

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
- Celery 任务内 LLM/FMP/SEC 异步调用用 `asyncio.run(...)` 包装（这些 client 是 async）。**事件循环边界（#15）**：`run_company_pipeline` 整体在一个 `asyncio.run` 内执行（discover/resolve/verify 共享一个 event loop），DB 写入用 `get_sync_session()` 在 loop 外/内均可（sync session 不依赖 loop）；避免每步新建 loop 的开销与 async client 跨 loop 复用报错

### 6.3 限流与并发
- Celery `rate_limit` 约束整体；`asyncio.Semaphore` 约束单任务内并发
- 跳过近期已跑公司：run 启动时按 `SupplyChainTask.updated_at > now - N days and status=success` 过滤（`SUPPLY_CHAIN_SKIP_RECENT_DAYS`，默认 7）

### 6.4 可选 beat
`app/core/celery_app.py` 配 beat schedule：每日增量刷新一部分低置信度关系（`SUPPLY_CHAIN_BEAT_ENABLED` 默认 false，先不开）。⚠️ **beat 必须单实例运行**（多副本会双触发定时任务）——Railway 上 beat 作为独立服务、`replicas=1`，或用 Redis 分布式锁兜底。

### 6.5 部署
`Procfile` 新增：
```
worker: /app/.venv/bin/celery -A app.core.celery_app worker --loglevel=info -Q supply_chain
beat: /app/.venv/bin/celery -A app.core.celery_app beat --loglevel=info
```
Railway 新增 worker 服务（与 web 共享镜像，启动命令不同）。

## 7. 稳定性与限流恢复（MiniMax 5 小时窗口）

> 现有 `llm_service` 的 tenacity 指数退避（2-10s）+ 多模型循环 fallback 针对的是「单次调用瞬时失败」。本节处理另一量级问题：**长时窗配额耗尽（如 MiniMax 5 小时上限）+ 额度恢复后自动续跑**。两层不能混在一起——对 5 小时窗口做 10s 退避重试 3 次必然失败、还会白白耗尽重试配额把任务误标 failed。

### 7.1 LLM 调用层：区分「瞬时限流」与「额度耗尽」+ 跨 provider fallback（#7）

在 `llm_service` 捕获 `RateLimitError` 时解析错误体，区分两种情况：

- **瞬时限流**（窗口秒级滚动）：保留现有指数退避重试（`_invoke_with_retry`）
- **额度耗尽**（5 小时长窗口）：抛新异常 `LLMQuotaExhausted(provider, retry_after_hint)`。**关键**：`LLMQuotaExhausted` **继承自 `OpenAIError`**，使现有 `_fallback_loop` 能 catch 它并**自动切换到 registry 里其他 provider**（openai/claude 等）顶上继续跑——不浪费 5 小时干等

判定逻辑：
- 优先用 MiniMax 响应里的 `retry_after` / 限流类型字段（按 MiniMax 错误码与响应体解析）
- 兜底用错误消息关键词（"quota"/"5 小时"/"rate limit window" 等）+ 配置的固定窗口 `SUPPLY_CHAIN_QUOTA_WINDOW_SECONDS`（默认 18000=5h）
- 解析不出则保守按「额度耗尽」处理（宁可多等，不要误判成瞬时把任务标 failed）

**全 provider 耗尽才暂停**：`_fallback_loop` 遍历完所有模型若都抛 `LLMQuotaExhausted`，把异常向上抛给 Celery 任务层（此时才进入 §7.2 暂停），否则只要有一个 provider 没耗尽就继续用它跑。

> 改动范围：`app/services/llm/service.py` 新增 `LLMQuotaExhausted(OpenAIError)` 异常 + 在 `_invoke_with_retry` / `_fallback_loop` 里识别。这是对现有 LLM 服务的**通用增强**，其他模块也受益。

### 7.2 任务层：限流感知的延迟重投

`process_company` 的重试策略分两路：

- **普通异常**（网络/超时/瞬时限流或其他非配额错误）：`autoretry_for`，指数退避，`max_retries` 用普通配额（保持现有 3 次）
- **`LLMQuotaExhausted`（全 provider 耗尽）**：走**专门的延迟重投路径**：
  1. 当前 task 置 `status=paused_quota` + `resume_after = now + 预估恢复时间`，`quota_retries += 1`
  2. 不计普通 `retries` 配额（额度等待不是「出错」）
  3. 用 `process_company.apply_async(args=[run_id, ticker], countdown=resume_after - now)` 延迟重投——countdown 可达数小时
  4. `quota_retries` 上限 `SUPPLY_CHAIN_MAX_QUOTA_RETRIES`（默认 10，封顶防卡死）

### 7.3 批次层：run 级熔断 + 额度恢复自动续跑（核心，#8 #9）

**run 级熔断（#8）**：`run_supply_chain_batch` 一次性 `delay` 全部 ticker 后，任务已入队，无法靠「暂停派发」阻止。改在 `process_company` **执行开头检查** `run.status`：
- 若 `paused_quota` → **不执行**，`process_company.apply_async(countdown=run.resume_after - now)` 自我延迟重投，避免 4 个并发 worker 连续撞限流
- 这保证熔断即时生效，已入队任务不会盲跑

`SupplyChainRun` 在全 provider 配额耗尽时进入 `paused_quota` 状态，并由**延迟续跑任务**在额度恢复窗口到期后自动恢复整批：

1. `process_company` 第一次抛 `LLMQuotaExhausted`（全 provider 耗尽）时：
   - 置 run `status=paused_quota`、`quota_paused_at=now`、`resume_after` 取所有受影响 task 的最早恢复时间
   - 投延迟任务 `resume_run_if_quota_recovered.apply_async(args=[run_id], countdown=resume_after - now)`
2. `resume_run_if_quota_recovered(run_id)` 在延迟后执行：
   - 先发**探测调用**（极小 token，如单字 "ping"）验证额度
   - **探测自身被限流的处理（#9）**：探测调用 catch `LLMQuotaExhausted` = 视为「仍未恢复」**不报错**，进退避分支
   - **有额度** → 置 run `running`、`probe_attempts=0`，重新 `delay` 所有 `paused_quota` 的 task，**续跑**
   - **仍未恢复** → `probe_attempts += 1`，再延迟一个探测窗口（指数退避：1 min → 5 min → 15 min，封顶 `SUPPLY_CHAIN_MAX_PROBE_ATTEMPTS=10`），避免无限探测；超过上限则置 run `failed` 并记录原因（需人工介入）

这样即使配额在凌晨 3 点恢复，系统也会自动续跑，无需人工介入。

### 7.4 任务管理 API 对接

`/runs/{run_id}/resume` 手动恢复接口也复用 `resume_run_if_quota_recovered` 的逻辑（强制探测+续跑）。前端任务看板对 `paused_quota` 状态显示「⏸ 配额等待中，预计 HH:MM 恢复」徽标 + 剩余恢复倒计时，并允许「立即重试」。

### 7.5 章节小结：稳定性策略

| 故障类型 | 处理 | 重试上限 |
|---------|------|---------|
| 网络超时 / 瞬时 429 | tenacity 指数退避（现有） | `MAX_LLM_CALL_RETRIES=3`（单次调用）|
| 单模型失败 | 多模型循环 fallback（现有） | registry 长度 |
| 单 provider 配额耗尽 | `LLMQuotaExhausted` 被 fallback catch → 切其他 provider 顶上 | registry 长度 |
| 全 provider 配额耗尽 | run 级熔断 `paused_quota` + task `countdown` 延迟重投 | `SUPPLY_CHAIN_MAX_QUOTA_RETRIES=10`（按 task）|
| 额度恢复续跑 | `resume_run_if_quota_recovered` 探测（限流=未恢复）+ 整批恢复 | `SUPPLY_CHAIN_MAX_PROBE_ATTEMPTS=10` |
| 完全失败 | 标 `failed`，前端可 `retry-failed` 重投 | — |

## 8. API + 前端

### 8.1 后端路由（`app/api/v1/supply_chain_map.py`，前缀 `/supply-graph`）
> 与现有 `/supply-chain`（FinReflect 图谱）区分，避免冲突。在 `api.py` 注册。
- `POST /supply-graph/companies/{ticker}/run` —— 单公司按需（创建 single run，触发 `process_company.delay`）
- `POST /supply-graph/runs` —— body `{universe}` 触发 batch run
- `GET /supply-graph/runs` / `GET /supply-graph/runs/{run_id}` —— 运行列表/详情（含 task 列表与进度）
- `POST /supply-graph/runs/{run_id}/pause` / `/resume` / `/retry-failed` —— 控制（pause=置 `paused`，task 执行前自检熔断；retry-failed=重投 failed 任务）
- `GET /supply-graph/graph?ticker=&depth=1` —— 取以 `ticker` 为中心、`depth` 度邻域的子图（后端用递归 CTE 一条 SQL 查 N 度，再 `GiraffeGraph` 装载 + `page_rank` 截断，`to_dict()` 输出 camelCase）。`depth ≤ 3` 硬上限（见 §8.3）
- `GET /supply-graph/graph/expand?from_node_id=&depth=1` —— 漫游：以当前某节点为新焦点增量拉取邻域，前端 merge 进已有图。支持 `direction=upstream|downstream|both`（下游走 `CUSTOMER_OF` 边）、`depth ≤ 3`
- `GET /supply-graph/edges/{edge_id}/clues` —— 取该关系的线索列表（按 `stance`/`filing_date` 排序）
- `GET /supply-graph/nodes/{node_id}/detail` —— 节点详情（公司画像 + 入度/出度 + 关键供应关系摘要）

遵循分层规则：路由只做参数解析 + 调 service；service 在 `app/services/supply_chain/`。

### 8.3 多度查询性能策略（A+C 组合，不引入图数据库）

> 关系表存邻接表的通病:多度遍历需递归 JOIN / 多次往返,3-4 度指数级放大。下游扩展受限于①性能②私有节点断链③前端渲染。策略:

**A. 受控扩展 + 重要性截断（应用层）**
- 后端 BFS 硬上限:`depth ≤ 3`、`max_nodes ≤ 200`、`max_edges ≤ 500`,超限截断并返回 `truncated=true` 标志
- 遇 `expandable=false` 节点**停止该分支**(私有/境外,无上游可追,不无意义查询)
- 截断按 importance:用 `GiraffeGraph.page_rank(seed)` 算关键节点,按 `confidence × degree` 排序保留 Top-N 路径,不让长尾节点淹没前端
- 前端 G6:节点数 > 300 时**折叠聚合**(次要供应商聚成「其它供应商」虚节点),保证渲染流畅

**C. 递归 CTE 单 SQL 多度查询（DB 层）**
- `app/services/supply_chain/graph_query.py`:用 PostgreSQL **递归 CTE** 一条 SQL 查出 N 度子图,把 N 次往返压成 1 次——3 度查询从秒级降到 100-300ms
- SQL 草案(`direction=both`,按 `edge_type` 过滤方向):
  ```sql
  WITH RECURSIVE bfs AS (
    SELECT edge_id, src_node_id, dst_node_id, edge_type, 1 AS d
    FROM supply_chain_edges
    WHERE dst_node_id = :seed OR src_node_id = :seed
    UNION ALL
    SELECT e.edge_id, e.src_node_id, e.dst_node_id, e.edge_type, b.d + 1
    FROM supply_chain_edges e
    JOIN bfs b ON e.src_node_id = b.dst_node_id OR e.dst_node_id = b.src_node_id
    WHERE b.d < :depth
  )
  SELECT DISTINCT edge_id, ... FROM bfs;
  ```
- 递归 CTE 配合 `(src_node_id)`、`(dst_node_id)` 双向索引(§4.1 已有 `dst_node_id` 索引,补 `src_node_id` 索引)
- 防环:递归 CTE 用 `UNION`(去重)而非 `UNION ALL`,或在 visited 集合里排除已访问节点

**B. 可选图缓存（Redis，热门公司）**
- 高频 `(seed_node_id, depth, direction)` 子图序列化为 GiraffeGraph JSON 缓存,TTL 1-7 天
- 增量更新(run 重跑某 ticker)时失效相关缓存
- 首次查询仍走 CTE,缓存只加速重复查询

**结果**:3 度任意方向查询稳定 100-300ms、前端流畅、不假装能追到原材料端(断链节点显式停止 + truncated 标志)。4 度不开放(收益递减、性能与渲染都吃紧)。

### 8.2 前端（Next.js，`TopNav` 注册）

**技术选型**：采用 **AntV G6 v6**（`@antv/g6@^6`）。G6 是专为关系图谱设计的图分析引擎（区别于 xyflow 的「节点画布」定位），内置力导/层次/辐射/dagre 等多种布局、WebGL 高性能渲染、节点聚合/过滤/图分析算法，更适合供应链图谱「单公司中心 + 可漫游 + 节点边可能上千」的探索体验。现有 `/supply-chain` 页的 `@xyflow/react` 组件保持不变，新页面独立用 G6，两套不互相干扰。

> ⚠️ **实施首步必须验证兼容性**：G6 v6（2025 年发布）与 React 19 + Next.js 16 的集成需先跑通一个最小 demo（SSR 关闭、`'use client'`、动态 import）再铺开。本项目 Next.js 版本较新，前端编码前先查 `frontend/node_modules/next/dist/docs/`（见 `frontend/AGENTS.md`）。若 G6 v6 兼容性阻断，回退到 `@antv/g6@^5`。实施阶段涉及视觉细节时用 frontend-design skill 打磨。

**焦点模式：单公司中心 + 可漫游（支持 3 度上下游）**
- 默认以某家公司为种子展示其供应商图谱（`depth=1`，即直接上游供应商）；单次数据量小、加载快、贴合「查这家公司供应链」的直觉
- 双击节点 → 以该节点为新焦点 `expand`，前端按 G6 的 graph data 增量合并（按 `node_id`/`edge_id` 去重）+ `fitView` 聚焦
- 顶部搜索框：输入 ticker/公司名定位并切换焦点公司
- **深度/方向控制**：可选 1/2/3 度、上游/下游/双向(下游走 `CUSTOMER_OF`)；4 度不开放(见 §8.3)
- **truncated 提示**:后端返回 `truncated=true` 时,前端顶部显示「已按重要性截断至 Top-N,完整图过大」徽标

**G6 集成要点**：
- G6 实例仅在客户端创建（Next 16 SSR 下用 `dynamic(() => import(...), { ssr: false })` 或 `useEffect` 内挂载）
- 数据契约对齐 §3 的 `GiraffeGraph.to_dict()`（camelCase：nodes `{nodeId,nodeType,properties}` / edges `{srcType,srcId,dstType,dstId,edgeType,timestamp,properties}`）——但 **G6 期望 `{id,source,target}` 形态，不能直接消费 giraffe 命名**，必须经 `SupplyGraphAdapter` 转换（`nodeId→id`、`srcId/dstId→source/target`、properties 展平为样式映射输入），adapter 同时负责漫游合并去重
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
- **节点**：节点大小按「被依赖度」（入度，作为多少家公司的供应商）映射，凸显关键供应商；节点配色按类型（company/supplier）；**私有/境外节点（`expandable=false`）用虚线边框 + 锁标**表明知识边界（硬伤 3）；hover 显示 name/ticker/aliases/description 气泡；**节点数 > 300 时折叠聚合次要供应商为「其它供应商」虚节点**（§8.3 A），保证渲染流畅
- **边**：粗细与颜色按 `confidence` 分档（<60 黄虚线动画、60-79 蓝、≥80 绿粗实线）；**`confidence_source=UNVERIFIED` 的边灰色 + ❓标**（仅 LLM 猜测无证据，区别于已验证）；`is_single_source=true` 加瓶颈图标；边 label 显示 `product`；hover tooltip 显示 `evidence_summary` + `confidence_source` 徽标；**`changed=true` 的边加「本期变化」脉冲**（变化检测）
- **线索抽屉**：点击边 → 右侧抽屉列出 `SupplyChainClue`，按 `source_type` 分组（电话会/新闻/SEC/变化），每条带 `stance` 色标（SUPPORT 绿/REFUTE 红/NEUTRAL 灰/CHANGED 紫）、原文 `snippet_text`、`document_url` 跳转、`filing_date`、`section`、`confidence_delta`
- **过滤**：置信度阈值滑块（实时过滤边，G6 的 `filter` API）、按 `confidence_source` 筛选（LLM/SEC_VERIFIED/UNVERIFIED/全部）、按 `product_category` 筛选、按 `edge_type`（上游/下游）切换、搜索高亮节点
- **导航**：G6 内置 Minimap 插件 + ToolBar 插件（缩放/居中/锁定）；面包屑记录漫游路径（A → B → C），可回退
- **状态反馈**：单公司按需 run 时，图谱区显示该 ticker 的 task 进度（DISCOVER→RESOLVE→EVIDENCE_VERIFY 阶段条 + 完成后自动刷新图谱）；轮询或 SSE 推送进度

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
SUPPLY_CHAIN_VERIFY_THRESHOLD=60     # verify 触发置信度阈值（硬伤2）
SUPPLY_CHAIN_GENERIC_SUPPLIERS=TSMC,Samsung,Intel,Google Cloud,AWS  # 万能答案黑名单，命中强制 verify
SUPPLY_CHAIN_SMALLCAP_MARKETCAP=2e9  # 低于此市值视为中小盘，强制 verify
SUPPLY_CHAIN_SKIP_RECENT_DAYS=7
SUPPLY_CHAIN_DISCOVER_MODEL=         # 空=用 DEFAULT_LLM_MODEL
SUPPLY_CHAIN_VERIFY_MODEL=           # 空=用 DEFAULT_LLM_MODEL
SUPPLY_CHAIN_BEAT_ENABLED=false
SUPPLY_CHAIN_DISCOVER_CACHE_TTL=604800  # 7 天，LLM 知识稳定，按日缓存浪费）
SUPPLY_CHAIN_TRANSCRIPT_QUARTERS=4   # verify 取最近几个季度电话会
SUPPLY_CHAIN_NEWS_LOOKBACK_DAYS=730  # verify 新闻回溯天数

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
- 成本控制：discover 结果按 ticker+日期缓存、允许 skipped 跳过无知识公司；跳过近期已跑公司；discover 用便宜模型；verify 触发面因「黑名单/中小盘/单一来源」扩大（预估 40-60% 关系进入 verify），但**电话会/新闻/SEC 各源缓存复用**（同 ticker 季度数据跨关系共享），单 ticker 取证成本可控。
- 6000 家 × Top 5-10 供应商，discover LLM 调用 ~6000 次；verify 作用于 40-60% 关系，电话会抓取 ~6000 次（4 季度 × 缓存）、新闻检索 ~6000 次、SEC ~2400-3600 次；**质量保障优先于成本**，宁可多取证也不要交付未验证猜测。
- **阶段 0（评估集先行）**：在阶段 1 前先建 ~50 条 ground truth，用 S&P 50 子集跑 discover，看 precision/校准，校准不达标先调 prompt 不放量。

## 11. 测试（TDD，`tests/services/supply_chain/`）

`asyncio_mode=auto`，LLM/FMP/SEC 全 mock，`@pytest.mark.slow` 标真实外呼。
- `test_fmp_universe.py`：名称→ticker 匹配（精确/别名/模糊/未命中）
- `test_resolver.py`：规范化去重、ticker 映射、命名实体回退
- `test_discover.py`：LLM 结构化返回解析、Top-N 截断、confidence 范围、`skipped` 返回路径、`customers` 反向关系解析
- `test_verify.py`：**多源独立取证**（电话会/新闻/10-K 各源独立抓取+独立落 clue，不命中即止）、关键词检索片段而非整份喂入（#6）、带立场线索抽取、综合重打分、只加不删、**零证据置 UNVERIFIED**
- `test_filter.py`：verify 触发条件四选一（低分/黑名单/中小盘/单一来源）
- `test_product_taxonomy.py`：`product_text` 归一到类目 ID
- `test_alias_resolver.py`：Foxconn/富士康/Hon Hai 别名归一为同一 node_id
- `test_market_cap.py`：FMP profile `marketCap` 落 `node.properties.market_cap` + 缓存（#5）
- `test_repository.py`：↔GiraffeGraph 映射、`edge_id`（不含 timestamp）verify 更新 timestamp 后仍幂等 upsert（#1）、`expandable=false` 节点写入
- `test_giraffe_graph.py`：摘取后的领域对象核心算法（sub_graph/trim_to_token_limit[KEY_PROPERTIES 已替换为供应链白名单]/to_dict/diff）回归（#2）
- `test_pipeline.py`：单公司 4 步端到端（mock 全外部依赖）
- `test_change_detection.py`：重跑 diff 标记新增/消失/置信度剧变关系为 `changed`
- `test_eval.py`：评估集 precision/recall + 置信度校准曲线（`@pytest.mark.slow`，真实 LLM）
- `test_graph_query.py`：递归 CTE 多度查询（1/2/3 度）、上下游方向过滤、`depth≤3` 硬上限、`max_nodes/max_edges` 截断返回 `truncated=true`、`expandable=false` 分支停止、防环（§8.3）
- `test_tasks.py`：task 状态机流转、重试、run 计数
- `test_quota_recovery.py`：`LLMQuotaExhausted` 识别、单 provider 耗尽时 fallback 到其他 provider（#7）、全 provider 耗尽时 task `paused_quota` 延迟重投、**run 级熔断**（task 执行前检查 `paused_quota` 自我延迟）（#8）、`resume_run_if_quota_recovered` 探测成功/失败两条路径、**探测调用被限流视为未恢复**（#9）、探测退避封顶、`probe_attempts` 超限置 failed
- 前端：`cd frontend && npx tsc --noEmit` 通过（含 G6 v6 与 React 19/Next 16 集成类型检查）

## 12. 落地清单（每完成一小步即提交）

1. 摘取 `giraffe_graph.py` 到 `app/services/supply_chain/domain/`，替换依赖 + **改造 KEY_PROPERTIES/删除 fifo/edge_id 去timestamp**（#1 #2）（+ `uv add networkx pandas`，含测试）
2. 五张 SQLModel 表 + alembic 迁移
3. `fmp_universe.py` 全市场股票池 + 名称→ticker 匹配（含测试）
4. `product_taxonomy.py` 产品类目本体 + 归一（含测试）
5. `alias_resolver.py` 供应商别名归一（含测试）
6. `repository.py` ↔GiraffeGraph 映射 + upsert（含测试）
7. `discover.py`（含 skipped/customers 路径，含测试）
8. `resolve.py`（含断链 expandable 标记 + **market_cap 落库** #5，含测试）
9. `filter.py` verify 触发条件四选一（含测试）
10. `verify.py` 多源独立取证 + **关键词检索片段**（#3 #6，含零证据 UNVERIFIED，含测试）
11. `pipeline.py` 单公司编排（含测试）
12. `change_detection.py` 重跑 diff 标记变化（含测试）
13. `app/core/celery_app.py` + `app/tasks/supply_chain.py`（含测试）
13b. `llm_service` 新增 `LLMQuotaExhausted` + 限流识别；`process_company` 配额延迟重投；`resume_run_if_quota_recovered` 探测续跑（含 `test_quota_recovery.py`）
14. **评估集** `evals/supply_chain/`（~50 条 ground truth）+ `test_eval.py` precision/recall/校准曲线
15. `graph_query.py` 递归 CTE 多度查询 + 重要性截断 + 方向过滤（含测试，§8.3）
16. 后端路由 `/supply-graph`（含测试）
17. 配置项 + `.env.example`
18. 前端：**先验证 G6 v6 与 React 19/Next 16 最小集成**（`'use client'` + 动态 import + SSR 关闭 demo），通过后再铺开；若阻断回退 `@antv/g6@^5`
19. 前端图谱页（G6 canvas + 漫游 + 3 度上下游 + 线索抽屉 + 过滤 + UNVERIFIED/断链/变化标记/折叠聚合展示） + 任务看板页（shadcn 表格） + `lib/api/supplyGraph.ts`
20. `Procfile` worker/beat + 文档（README 补充启动方式）
21. `make check`（ruff + pyright）+ 前端 `tsc --noEmit` 通过

## 13. 已知盲区与边界（坦诚声明）

本系统产出的是**「带置信度与证据链的、美股上市公司直接上下游的近似供应链图」**，非「整个美股供应链」。已知盲区：

- **SEC 文件多不披露供应商**：verify 不依赖 10-K 单一源，已级联电话会/新闻/8-K，但仍可能零证据（标 `UNVERIFIED`，不伪装已验证）
- **LLM 知识覆盖与过度自信**：中小盘公司可能 `skipped`；万能答案黑名单 + 强制 verify + 校准函数缓解，但无法根除
- **图在私有/境外供应商处断链**：`expandable=false` 显式标记，无法追溯至原材料端（除非接入付费供应链数据，本期不做）
- **下游关系残缺**：通过 discover 顺便问客户（`CUSTOMER_OF`）+ 10-K 大客户披露部分补全，但私有供应商的客户仍缺失
- **产品归一与别名归一非完美**：轻量本体 + 别名表覆盖常见类目/实体，长尾仍可能重复或错并
- **时效性**：变化检测（`changed` 标记）+ beat 聚焦刷新缓解，但非实时

## 14. 不在本期范围（YAGNI）

- 图数据库（Neo4j/AGE）持久化——当前规模 SQLModel + JSON 属性足够
- 全市场一次性同步跑完——分阶段 + beat 增量
- 供应商财务健康度评分、替代供应商推荐——未来扩展
- 接入付费供应链数据源（如 Panjiva/ImportGenius）弥补断链——未来扩展
- 与现有 `/supply-chain` FinReflect 图谱合并——保持解耦