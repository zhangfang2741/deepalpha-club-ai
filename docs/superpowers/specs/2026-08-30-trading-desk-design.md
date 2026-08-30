# 交易台（Trading Desk）—— 多智能体交易分析台 设计文档

日期：2026-08-30
状态：待实施

## 1. 背景与目标

开源项目 TradingAgents 的 agent 逻辑不错，但交互体验很差：CLI 跑一遍、黑盒等很久、最后吐一大坨文本，看不到过程、无法介入。

本模块在 deepalpha-club-ai 的「AI 工具」下新增一个**体验优先**的多智能体交易台，把 TradingAgents 缺的四块补上：

1. **Token 级流式推理** —— 每个 agent 的思考实时逐字推给前端，而不是等结果。
2. **多空辩论可视化** —— 研究员的对辩分轮次、分左右呈现，谁在反驳谁一目了然。
3. **决策逐步组装** —— 各 agent 的信号实时汇入共识条，最终裁决卡带完整审计链。
4. **人在环（HITL）** —— 运行中可暂停、可注入人工意见到共享上下文，下游 agent 会纳入。

**第一期范围**：上述四项 + 运行落库与历史回看。

**非目标（第一期明确不做）**：真实下单/券商对接、实盘资金、回测引擎、移动端专门优化（响应式够用即可）。这是研究/分析工具，不碰真实交易。

**推迟到二期**：FMP 数据源替换、平台自研技术工具（缠论/威科夫/一目均衡表/机构信号）入阵、节点级成本与耗时面板、断点续跑。

### 与原始 FLOOR 文档的关系

`docs/FLOOR —— 多智能体交易台:实现说明(给 Claude Code)` 是本设计的需求来源，交互体感基准是 `floor-prototype-cn.html`。但该文档假设的是一个独立的 `floor/` 项目（Vite + 独立 FastAPI + 无鉴权 + 自研 DAG orchestrator）。本设计将其重新落位到 deepalpha-club-ai：Next.js 16 App Router、复用平台 JWT 鉴权、复用现有 LangGraph/Redis/Postgres 基础设施，并且**不自研 DAG orchestrator**（理由见 §3）。

视觉上不沿用原型的暗色暖中性调，改为与平台其余页面统一的浅色方案（详见 §8）。

## 2. 关键技术验证（已实跑确认）

以下结论均为实际执行验证，非推断：

| 验证项 | 结论 |
|---|---|
| `uv add tradingagents==0.7.0` 直接安装 | ❌ 失败。`tradingagents` 要求 `redis>=7.4.0`，而 `celery[redis]` → `kombu` 把 redis 锁在 `<6.5`。Celery 被 supply_chain 模块重度使用（Procfile 有 worker/beat），不能移除。 |
| `redis` 是否真实依赖 | ❌ 幽灵依赖。TradingAgents 全源码**从未 import redis**。`backtrader` / `chainlit` / `parsel` 同理。 |
| `pandas>=3.0.2` 是否必需 | ❌ 非必需。实际只用了 `pd.Timestamp` / `pd.bdate_range` / `pd.to_datetime` 与基础 DataFrame 索引，pandas 2.x 完全满足。 |
| 加 `[tool.uv] override-dependencies` 后解析 | ✅ 通过 |
| 实际 `uv sync` + import + 与现有栈共存 | ✅ `tradingagents 0.7.0` / `pandas 2.3.3` / `redis 6.4.0` / `celery 5.6.3` / `langchain 1.3.18` / `langgraph 1.2.11` 同时跑通 |
| `CompiledStateGraph.builder` 重编译加 checkpointer + `interrupt_before` | ✅ 跑通「中断 → `aupdate_state` 注入 → 恢复」完整链路 |

**结论**：TradingAgents 可以在同进程直接引入，不需要拆微服务或独立 venv。代价是 `pyproject.toml` 需要一段依赖覆盖，且因为 `tradingagents/llm.py` 无条件 import 了 xai / ollama / litellm / openrouter / huggingface，会多装约 100 个包（不冲突，但镜像会变大）。

### TradingAgents 0.7.0 能力盘点

| 需求 | 现状 | 处理 |
|---|---|---|
| Token 级流式 | `propagate()` 是同步的，只到 message 粒度 | 绕开 `propagate()`，自己 `astream(stream_mode=["messages","updates"])`，token 用 `metadata["langgraph_node"]` 归属 |
| 多空辩论 | `InvestDebateState`（bull/bear history + count）、`RiskDebateState`（激进/中立/保守 + count） | 数据齐全，可分轮分边渲染 |
| 结构化裁决 | `TradeRecommendation`（signal / confidence / size_fraction / target_price / stop_loss / time_horizon_days / rationale / warning_message） | 直接作为 `verdict` 事件载荷 |
| 分析师信号 `{dir, conf}` | ❌ 不产出，只有大段文字 report | **需自建** `signal_extract.py`（见 §4） |
| HITL 暂停/注入 | ❌ `workflow.compile()` 裸编译，无 checkpointer、无 interrupt | **需自建**，见 §5 |
| 中文输出 | ✅ `TradingAgentsConfig.response_language` | 直接配置为中文 |
| 辩论轮数 | ✅ `max_debate_rounds` / `max_risk_discuss_rounds` | 暴露为配置项 |
| 数据源 | yfinance（行情+基本面）+ Google News RSS。无 FinnHub、无 Reddit | 第一期直接用，**不需要新增任何 API key** |
| 工具可替换性 | `ANALYST_TOOL_REGISTRY` 是模块级 dict，14 个 tool 可整体替换 | 为二期 FMP 替换预留 |

## 3. 架构决策

### 3.1 引擎抽象切在「整条流水线」这一层

`TradingEngine` 的契约是：**给定标的与人工意见，产出 Event 异步流**。DAG 编排属于引擎内部，不上浮。

因此本设计**不自研 DAG orchestrator**（与 FLOOR 文档 §3 不同）。TradingAgents 的真实拓扑原样呈现——4 位分析师 → 情境摘要 → 多空辩论 → 研究主管 → 交易员 → 激进/中立/保守三方风控辩论 → 风控裁决，前端流程条由 `run.started` 事件动态渲染。

理由：这是「用它而不抄它」唯一自洽的切法。若固定成 FLOOR 文档 §3.1 的七节点 DAG，就必须把 TradingAgents 拆开重组（等于抄了一半），且会丢掉它的三方风控辩论。将来接 ai-hedge-fund 只需再写一个 adapter，前端壳与事件协议不动。

代价：不同引擎的流程条长得不一样。这是可接受的——引擎的差异本来就该被看见。

### 3.2 运行托管：后台 asyncio task + Redis Stream 事件总线 + SSE 消费

`POST /runs` 立即返回 `run_id`，图在后台任务中执行，事件写入 Redis Stream；`GET /runs/{id}/stream` 从 Stream 消费并推 SSE。

- Redis Stream 自带自增 ID，直接映射事件协议的 `seq` 与 SSE 的 `Last-Event-ID`，断线重连即从该 ID 续读
- 刷新页面、多标签页可接回同一个 run
- pause / inject 走 Redis 标志位与队列，同进程协调最简单
- checkpointer 复用 `app/core/langgraph/graph.py` 中已有的 `AsyncPostgresSaver` 连接池

已排除的方案：
- **SSE 长连接内直接跑图**：断线即丢运行、Railway 有请求超时、刷新即失，与「落库 + 回看」直接冲突。
- **Celery worker 跑图**：worker 是同步的，`astream` 要包 `asyncio.run`，HITL 的 pause/inject 还需跨进程协调。第一期不值这个复杂度。

## 4. 事件协议（前后端契约）

后端通过 SSE 推送 JSON 事件。前端只认这套 schema，任何引擎都必须映射成它。**这层抽象是「前端壳可复用、后端引擎可替换」的关键。**

通用信封：

```jsonc
{ "type": "<event_type>", "run_id": "...", "seq": 12, "ts": 1788000000, "data": { ... } }
```

以 FLOOR 文档 §4 为基础，做了四处修改：

### 4.1 `run.started` 携带引擎自报拓扑

引擎 = 整条流水线，节点不能写死在前端。

```jsonc
{ "type": "run.started", "data": {
    "ticker": "NVDA", "trade_date": "2026-08-30",
    "engine": "tradingagents/0.7.0",
    "capabilities": { "supports_pause": true, "supports_inject": true, "supports_resume_after_restart": false },
    "stages": [
      { "id": "market_analyst",   "name": "技术面分析师", "role": "价格行为", "group": "analyst" },
      { "id": "social_analyst",   "name": "社交情绪",     "role": "舆情",     "group": "analyst" },
      { "id": "news_analyst",     "name": "消息与新闻",   "role": "资讯流",   "group": "analyst" },
      { "id": "fundamentals_analyst", "name": "基本面分析师", "role": "价值", "group": "analyst" },
      { "id": "situation_summary","name": "情境摘要",     "role": "汇总",     "group": "system"  },
      { "id": "bull_bear_debate", "name": "研究员辩论",   "role": "多空对辩", "group": "debate"  },
      { "id": "research_manager", "name": "研究主管",     "role": "裁定",     "group": "manager" },
      { "id": "trader",           "name": "交易员",       "role": "综合",     "group": "trader"  },
      { "id": "risk_debate",      "name": "风控委员会",   "role": "三方评议", "group": "debate"  },
      { "id": "risk_judge",       "name": "风控裁决",     "role": "最终决策", "group": "manager" }
    ] } }
```

### 4.2 辩论事件泛化（支持两场辩论）

FLOOR 文档的 `side` 只有 `bull|bear`，但 TradingAgents 有**两场**辩论：研究员多空辩论，以及激进/中立/保守三方风控辩论。

```jsonc
{ "type": "debate.turn", "data": {
    "stage_id": "risk_debate",
    "debate_id": "risk",              // "research" | "risk"
    "side": "aggressive",             // 引擎自定义门派 id
    "side_label": "激进派",
    "polarity": "bull",               // bull | bear | neutral —— 前端据此染色与分栏
    "round": 2,
    "turn_id": "risk-r2-aggressive" } }
```

`polarity` 让前端无需认识具体门派即可决定配色与左右分栏；三方辩论渲染为三色分栏。

### 4.3 `agent.token` 挂 `turn_id`

一个辩论 stage 会产生 4~6 张卡片，仅靠 `stage_id` 累加会串台。

```jsonc
{ "type": "agent.token", "data": { "turn_id": "...", "text": "增量片段" } }
```

`agent.token` 是**增量**，前端按 `turn_id` 累加到对应卡片。

### 4.4 `verdict` 对齐 `TradeRecommendation`

```jsonc
{ "type": "verdict", "data": {
    "signal": "BUY",                  // BUY | SELL | HOLD
    "confidence": 0.66,               // 0-1，前端渲染为 66%
    "size_fraction": 0.04,            // 0-1
    "entry_reference_price": 178.2,
    "target_price": 205.0,
    "stop_loss": 163.9,
    "currency": "USD",
    "time_horizon_days": 21,
    "rationale": "……",
    "warning_message": null } }
```

`warning_message` 由 TradingAgents 在 JSON 解析失败走 fallback 时置位。**必须在裁决卡上显式展示**，否则用户会把降级解析出的结论当作正常结论。

### 4.5 完整事件类型表

| type | data 字段 | 说明 |
|---|---|---|
| `run.started` | `{ ticker, trade_date, engine, capabilities, stages }` | 初始化 pipeline |
| `stage.active` | `{ stage_id }` | 某节点开始 |
| `stage.done` | `{ stage_id }` | 某节点完成 |
| `turn.started` | `{ turn_id, stage_id, name, role, avatar }` | 新建一张推理卡片 |
| `agent.tool_call` | `{ turn_id, tool, args? }` | agent 调用工具（前端显示 ⚙ chip） |
| `agent.token` | `{ turn_id, text }` | 流式 token 增量 |
| `turn.done` | `{ turn_id }` | 该卡片文本结束 |
| `agent.signal` | `{ stage_id, turn_id, name, dir, conf, extracted }` | 结构化信号（`extracted=true` 表示由 §4.6 抽取而非引擎原生产出） |
| `debate.turn` | `{ stage_id, debate_id, side, side_label, polarity, round, turn_id }` | 辩论轮次 |
| `human.note` | `{ text, injected_into }` | 人工注入的意见 |
| `consensus.update` | `{ bull, neutral, bear, lean }` | 共识计数更新 |
| `run.paused` / `run.resumed` | `{ at_stage_id }` | HITL 状态切换，前端据此切按钮态 |
| `verdict` | 见 §4.4 | 最终裁决 |
| `run.finished` | `{ status, duration_ms }` | 结束 |
| `error` | `{ stage_id?, message, fatal }` | 错误 |

### 4.6 信号抽取（自建，非引擎自带）

TradingAgents 的分析师不产出 `{dir, conf}`，只产出大段文字 report。而共识条与流程条上的信号 chip 全靠它。

`signal_extract.py`：每份 report 完成时，用 `llm_registry` 的快模型（haiku / gpt-4o-mini）做一次结构化抽取，产出 `{dir, conf}` 并发 `agent.signal`（`extracted: true`）。

约束：
- 额外 LLM 调用约 +6 次/run，计入成本预期
- 抽取失败**降级为 `neutral` 并在 chip 上标注「未能判读」**，不静默编造方向
- `extracted` 字段让前端能把「引擎原生信号」与「我们抽取的信号」区分展示

## 5. 引擎接口与 HITL

### 5.1 接口定义（`engine_base.py`）

```python
class EngineCapabilities(BaseModel):
    supports_pause: bool
    supports_inject: bool
    supports_resume_after_restart: bool

class TradingEngine(Protocol):
    name: str
    capabilities: EngineCapabilities
    def describe(self) -> EngineDescriptor: ...            # 拓扑，喂给 run.started
    async def astream(self, ctx: RunContext) -> AsyncIterator[Event]: ...
```

`RunContext` 携带：`run_id`、`ticker`、`trade_date`、`ControlHandle`（查暂停标志、取人工意见队列）、LLM 配置。

能力声明不是摆设：前端据 `capabilities` 决定「暂停」「注入意见」按钮是否可用。将来的引擎若不支持中途注入，按钮自然置灰，而不是点了没反应。

### 5.2 暂停

```python
compiled = ta_graph.graph.builder.compile(
    checkpointer=async_postgres_saver,
    interrupt_before=AGENT_NODES,
)
```

`AGENT_NODES` 只包含语义节点（4 位分析师、Situation Summariser、Bull/Bear Researcher、Research Manager、Trader、Aggressive/Neutral/Conservative Analyst、Risk Judge，共 13 个），**不包含** `tools_*` 与 `Msg Clear *` 管道节点——否则中断点会碎得无法使用。

runner 主循环：跑到节点边界 → 自动恢复；暂停标志置位时停在边界等待。**暂停天然发生在节点边界**，不会截断某个 agent 的推理。

### 5.3 注入（有意的嫁接）

下游节点实际读取的 state 字段（已核查源码）：

| 节点 | prompt 中真正读取的字段 |
|---|---|
| 多头/空头研究员、研究主管 | `market_report` / `sentiment_report` / `news_report` / `fundamentals_report` |
| 交易员 | `investment_plan` |
| 激进/中立/保守、风控裁决 | `trader_investment_plan` + 上述四份 report |
| （所有节点） | `situation_summary` —— **仅用于 BM25 记忆检索，不进 prompt** |

直觉上最该写入的 `situation_summary` 是陷阱：写进去只影响历史记忆检索，下游 prompt 根本看不到。FLOOR 文档 §3.2 所说的「追加进 blackboard 的 `human_notes`」在 TradingAgents 中没有对应物——它的 `AgentState` 没有给人类留位置。

因此注入必然是一次**有意的嫁接**：

- 交易员阶段之前的注入 → 以带分隔符的块追加到 `news_report` 尾部（选它是因为人工意见多为「你们漏了某个风险/事件」，与新闻情报同类）
- 交易员阶段之后的注入 → 追加到 `trader_investment_plan`
- 通过中断点的 `aupdate_state` 写入，并同时发 `human.note` 事件（含 `injected_into` 字段，说明写进了哪个字段）

**UI 不跟着撒谎**：前端渲染走事件流而非 state，人工意见在界面上始终是独立的蓝色 human 卡片，不会混入「消息与新闻分析师」那张卡。

**这是设计中唯一尚未实测的环节。** 中断/更新/恢复的机制本身已验证，但注入文本是否确实出现在下游 researcher 的最终 prompt 中尚未验证。实施计划中必须包含一个**前置验证步骤**：用假 LLM 跑一遍图，断言注入文本出现在下游 prompt 中。该步骤不通过则不继续往下实现。

## 6. 目录结构与分层

```
app/api/v1/trading_desk.py              路由：runs / stream / control / history
app/schemas/trading_desk.py             事件协议 + 请求响应（协议单一真源）
app/services/trading_desk/
  events.py            Event 信封 + 各 data 类型
  engine_base.py       TradingEngine Protocol + EngineCapabilities + RunContext
  engines/
    tradingagents.py   TradingAgents 适配器
    mock.py            回放固定事件序列，不调 LLM
  runner.py            运行编排：后台任务、pause/inject 控制、生命周期
  event_bus.py         Redis Stream 读写（seq、重放、TTL）
  signal_extract.py    从 report 抽 {dir, conf}
  persistence.py       落库
app/models/trading_desk_run.py          TradingDeskRun（继承 UUIDModel）
app/cache/trading_desk_cache.py         控制标志位 + 人工意见队列

frontend/app/trading-desk/page.tsx
frontend/components/trading_desk/       Topbar / Pipeline / StreamPanel / TurnCard /
                                        DebateTurn / HumanNote / ConsensusMeter /
                                        VerdictCard / AuditChain / InjectBar / RunHistory
frontend/lib/api/trading_desk.ts        Axios（普通接口）+ 原生 fetch（SSE）
frontend/lib/store/trading_desk.ts      Zustand，事件 reducer
```

遵循平台分层规则：`api/v1/` 只做请求解析与调用 service；业务逻辑在 `services/`；Redis 操作在 `app/cache/`；`models/` 只定义表结构。

### 两处刻意的选择

**`engines/mock.py` 从第一天就存在。** FLOOR 文档 §2 的阶段 A 是「前端接本地 mock 事件源」，本设计把 mock 提升为后端的正式引擎实现。这样前端联调、runner/SSE/HITL 的集成测试、CI 全都不需要真实 LLM；同时它是「引擎可替换」抽象的第一个验证者——若 MockEngine 与 TradingAgentsEngine 能共用一个接口，将来 ai-hedge-fund 就也能。

**SSE 用原生 fetch。** 项目规则要求前端统一走 Axios，但 Axios 读不了流式响应体。`app/chat/page.tsx` 与 `components/chat/ChatThread.tsx` 已是 `fetch` + `body.getReader()` 的先例，沿用同一套并在文件内注明原因；普通接口仍走 Axios 实例。

## 7. API 与数据模型

### 7.1 端点（前缀 `/api/v1/trading-desk`，复用平台 JWT 鉴权）

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/runs` | 创建 run，起后台任务，返回 `run_id` |
| `GET` | `/runs/{run_id}/stream` | SSE 事件流，支持 `Last-Event-ID` |
| `POST` | `/runs/{run_id}/control` | `{ action: "pause" \| "resume" \| "inject" \| "cancel", text? }` |
| `GET` | `/runs` | 历史列表（当前用户） |
| `GET` | `/runs/{run_id}` | 运行详情（回放用） |

### 7.2 落库与回放

一次 run 的 token 事件可能上万条，全量落库既贵又无意义：

- **Redis Stream** 存全量事件（含 token），TTL 7 天 —— 服务实时消费与断线重连
- **Postgres `TradingDeskRun`** 存结构化摘要：`user_id` / `ticker` / `trade_date` / `engine` / `status` / turns（每张卡片的**完整文本**，非逐 token）/ signals / verdict / audit / `duration_ms` / 时间戳 —— 服务历史列表与回放

回放按 turn 直接出全文，不逐字重播。

**审计链**不是独立事件类型，而是由 turn 序列派生：每个 `turn.done` 与 `human.note` 按时序构成一条目（谁、什么阶段、说了什么摘要）。前端实时运行时由 store 累积，回放时由 `TradingDeskRun.turns` 重建。人工意见在链中显式标注，使「这个结论受过人为干预」可追溯。

`status` 字段预留 `interrupted` 取值：因 checkpointer 是 Postgres，进程重启后图状态仍然存活，「续跑被中断的 run」结构上几乎白送。但它需要额外的状态机与 UI，**不在第一期实现**，仅在数据模型上不堵死这条路。

### 7.3 配置项（同步更新 `.env.example` 与 `app/core/config.py`）

```
TRADING_DESK_ENGINE=tradingagents             # 引擎选择
TRADING_DESK_LLM_PROVIDER=anthropic           # 传给 TradingAgentsConfig.llm_provider
TRADING_DESK_DEEP_MODEL=claude-sonnet-4-5     # 研究主管/交易员/风控裁决等深度节点
TRADING_DESK_QUICK_MODEL=claude-haiku-4-5     # 分析师节点 + 信号抽取
TRADING_DESK_MAX_DEBATE_ROUNDS=2
TRADING_DESK_MAX_RISK_ROUNDS=1
TRADING_DESK_EVENT_TTL_SECONDS=604800
```

模型默认值遵循平台既有约定（生产用 Claude Sonnet，轻量节点用 Haiku）。注意 TradingAgents 的 `llm_provider` 是 LangChain `init_chat_model` 的 provider key，与平台 `LLM_PROVIDER` 的取值空间不同，两者独立配置，不复用同一个变量。

`pyproject.toml` 需新增：

```toml
[tool.uv]
override-dependencies = ["redis>=5.2.1,<6.5", "pandas>=2.2,<3"]
```

并在该段加注释说明原因（TradingAgents 的 redis 依赖为幽灵依赖、pandas 3 约束过紧），避免后人误删。

## 8. 前端设计

### 8.1 视觉风格：与平台统一的浅色方案

不沿用 `floor-prototype-cn.html` 的暗色暖中性调。平台其余页面是 `bg-white` 卡片 + `gray-50` 底 + `blue-600` 顶栏，交易台走同一套语言。

- 背景/卡片：`#f8fafc` 底 + 白卡 + `#e2e8f0` 描边，`rounded-xl`
- 看多 `#16a34a` / 看空 `#ef4444` / 中性 `#d97706`（沿用平台既有约定）
- 强调色（系统消息、人工意见、工具 chip、光标）：`#2563eb`
- 等宽字体只用于数据、标签、信号、工具名；正文用 `system-ui, "PingFang SC"`

### 8.2 布局

三栏：左「交易台成员」流程条 / 中「实时推理」流 / 右「决策」面板。窄屏三栏堆叠，流程条转为横向滚动。

### 8.3 从原型继承的交互细节（不得丢失）

- 流式打字带闪烁光标，标点处停顿更长
- 节点状态：转圈（active）→ 打勾（done）并挂上该节点信号 chip
- 多空辩论左右错位、绿/红分色；三方风控辩论三色分栏
- 共识条三色按比例填充，带过渡动画
- 裁决卡置信度数字滚动到目标值
- 人工意见卡片用强调色，与 agent 卡片区分
- 尊重 `prefers-reduced-motion`：关闭打字动画，直接出全文
- 空态与错误态给方向，不只报错

### 8.4 文案与免责

界面全中文。按钮说清楚点了会发生什么（「开始分析」「暂停/继续」「注入意见」）。

页面底部常驻免责声明：**研究/分析用途，非投资建议，不执行真实交易**。UI 与代码注释中不得把 LLM 信号表述为投资建议——它是「agent 观点」，带置信度。

## 9. 测试策略

- `events.py` / `signal_extract.py` 的纯函数单测
- `MockEngine` 驱动 runner / event_bus / SSE / HITL 的集成测试，全程不调真实 LLM
- HITL 注入的前置验证（§5.3）：假 LLM 跑图，断言注入文本进入下游 prompt
- 涉及真实 LLM 的端到端测试标记 `@pytest.mark.slow`
- 测试目录镜像 `app/`：`tests/services/trading_desk/`
- 前端：`cd frontend && npx tsc --noEmit`

## 10. 实施顺序

每个阶段结束应可运行、可演示，再进入下一阶段。

| 阶段 | 内容 | 验收 |
|---|---|---|
| 0 | 依赖落地（`override-dependencies` + `uv add tradingagents`）；**HITL 注入前置验证**（§5.3） | `make check` 通过；注入验证测试通过。**此步不过则停止**，需回到设计层重找嫁接点 |
| 1 | 事件协议（`events.py` / `schemas`）+ `MockEngine` + `event_bus` + `runner` + SSE 端点 | MockEngine 驱动的集成测试跑通完整事件序列，含 pause/inject |
| 2 | 前端三栏 UI + Zustand 事件 reducer，接 MockEngine | 交互体感对齐原型：流式打字、辩论分栏、共识条、裁决卡、审计链、暂停/注入 |
| 3 | `TradingAgentsEngine` + `signal_extract` | 真实标的跑通一次完整分析，过程可看、可暂停、可注入 |
| 4 | 落库 + 历史列表 + 回放；导航注册；免责声明；响应式与 `prefers-reduced-motion` | 历史可列、可回看；`npx tsc --noEmit` 通过 |

阶段 2 先于阶段 3，是为了让交互体感在没有真实 LLM 成本与延迟的情况下打磨到位——这正是 FLOOR 文档 §2 阶段 A 的用意，只是 mock 源放在了后端。

## 11. 风险与已知取舍

| 风险 | 处理 |
|---|---|
| 依赖覆盖绕过了 TradingAgents 声明的约束 | 已源码核查 redis 未被 import、pandas 用法为基础 API；`pyproject.toml` 中加注释；升级 tradingagents 版本时需重新核查 |
| 多装约 100 个包（huggingface 等），镜像变大 | 接受。源于 `tradingagents/llm.py` 的无条件 import，非我方可控 |
| 注入嫁接点依赖 TradingAgents 内部字段语义 | 升级其版本时可能失效。以 §5.3 的前置验证测试作为回归防线 |
| 信号抽取是额外 LLM 调用，可能出错 | 失败降级为 `neutral` 并标注「未能判读」，事件中以 `extracted` 字段标明来源 |
| 一次完整分析成本较高（数十次 LLM 调用 + 6 次抽取） | 第一期不做成本面板（推迟二期），但 `TradingDeskRun` 记录 `duration_ms`，为二期留数据 |
| web 进程重启会中断在跑的 run | 接受。run 落库为 `interrupted` 状态，partial 结果可见；续跑推迟二期 |
