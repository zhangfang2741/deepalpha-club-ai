# 交易台后端骨架 实施计划（计划一 / 共三）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地交易台的依赖、事件协议与运行骨架，做到用 MockEngine 就能 `curl` 出一条完整的 SSE 事件流，并支持运行中暂停 / 恢复 / 注入人工意见。

**Architecture:** 引擎 = 整条流水线（给定标的产出事件异步流，DAG 编排在引擎内部）。`POST /runs` 起后台 asyncio 任务，事件写 Redis Stream；`GET /runs/{id}/stream` 从 Stream 消费推 SSE，Stream ID 直接充当 `Last-Event-ID` 实现断线重连。pause / cancel / inject 走 Redis 控制位，引擎在节点边界轮询。

**Tech Stack:** Python 3.13 / uv / FastAPI / Pydantic v2 / redis-py asyncio（Streams）/ LangGraph / pytest（asyncio_mode=auto）

**Spec:** `docs/superpowers/specs/2026-08-30-trading-desk-design.md`

---

## 计划拆分说明

Spec §10 定义了五个阶段。本计划覆盖**阶段 0 与阶段 1**，产出一个独立可测、可 `curl` 演示的后端骨架。

后续两个计划在本计划落地**之后**再写：

- **计划二**：前端交易台（spec 阶段 2）——依赖本计划产出的事件 schema 的确切形状
- **计划三**：TradingAgentsEngine + 信号抽取 + 落库回放（spec 阶段 3-4）——依赖本计划产出的 `TradingEngine` 接口与 runner 生命周期

现在就写后两个计划只能写出占位内容，因此不写。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `pyproject.toml` | 新增 `tradingagents` 依赖 + `[tool.uv] override-dependencies` |
| `app/core/config.py` | 交易台配置项（仅模块专属；LLM 复用平台统一配置） |
| `.env.example` | 同步配置项文档 |
| `app/schemas/trading_desk.py` | 事件协议 + 请求响应 schema（前后端唯一契约） |
| `app/services/trading_desk/engine_base.py` | `TradingEngine` Protocol / `RunContext` / `ControlHandle` |
| `app/services/trading_desk/engines/mock.py` | MockEngine：回放固定事件序列，不调 LLM |
| `app/cache/trading_desk_cache.py` | 运行控制位与人工意见队列的 Redis 操作 |
| `app/services/trading_desk/event_bus.py` | Redis Stream 事件读写（seq、重放、TTL） |
| `app/services/trading_desk/runner.py` | 后台任务编排与生命周期 |
| `app/api/v1/trading_desk.py` | 路由：runs / stream / control |
| `app/api/v1/api.py` | 注册子路由 |
| `tests/services/trading_desk/` | 测试，镜像 `app/` 结构 |

分层遵循项目规则：`api/v1/` 只做请求解析与调用 service；业务逻辑在 `services/`；Redis 操作在 `app/cache/`。

---

## Task 1: 依赖落地

TradingAgents 声明了 `redis>=7.4.0`，但源码从未 import redis（幽灵依赖），而本项目的 `celery[redis]` → `kombu` 把 redis 锁在 `<6.5`。同理它声明 `pandas>=3.0.2`，实际只用 `pd.Timestamp` / `bdate_range` / `to_datetime`。用 uv 的依赖覆盖绕过。

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 在 `pyproject.toml` 的 `dependencies` 数组末尾加入依赖**

找到 `[project]` 下的 `dependencies = [` 数组（`pyproject.toml:8` 起），在数组最后一项之后加入：

```toml
    "tradingagents==0.7.0",
```

固定精确版本：注入机制依赖它的内部实现细节（见 Task 2 / Task 3），不接受自动升级。

- [ ] **Step 2: 新增 `[tool.uv]` 段**

文件中当前不存在 `[tool.uv]` 段。在 `[tool.pytest.ini_options]` 段之前插入：

```toml
[tool.uv]
# TradingAgents 的依赖元数据与本项目冲突，但都是虚假冲突，故覆盖：
#   redis>=7.4.0  —— 幽灵依赖，其源码从未 import redis；而本项目的
#                    celery[redis] -> kombu 把 redis 锁在 <6.5，不能让步。
#   pandas>=3.0.2 —— 约束过紧，其实际用法只有 pd.Timestamp / bdate_range /
#                    to_datetime 与基础 DataFrame 索引，pandas 2.x 足够。
# 升级 tradingagents 版本时必须重新核查这两条是否仍然成立。
override-dependencies = [
    "redis>=5.2.1,<6.5",
    "pandas>=2.2,<3",
]
```

- [ ] **Step 3: 安装并验证共存**

```bash
uv sync
```

预期：解析成功并完成安装（会新增约 100 个包，源于 `tradingagents/llm.py` 无条件 import 了 xai / ollama / litellm / openrouter / huggingface，属预期内）。

- [ ] **Step 4: 验证 import 与关键版本**

```bash
uv run python -c "
import importlib.metadata as md
from tradingagents import TradingAgentsGraph, TradingAgentsConfig
import pandas, redis, celery
print('tradingagents', md.version('tradingagents'))
print('pandas', pandas.__version__, '| redis', redis.__version__, '| celery', celery.__version__)
"
```

预期输出包含 `tradingagents 0.7.0`、`pandas 2.x`、`redis 6.x`、`celery 5.x`。若 redis 变成 7.x 说明覆盖没生效，停下检查 `[tool.uv]` 段位置。

- [ ] **Step 5: 确认既有测试未被依赖变动打破**

```bash
uv run pytest -m "not slow" -q
```

预期：与本任务开始前一致（无新增失败）。

- [ ] **Step 6: 提交**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(trading-desk): 引入 tradingagents 并覆盖其幽灵依赖约束"
```

---

## Task 2: LLM 实例注入验证（阶段 0 门槛）

Spec §7.4：不引入第二套 LLM 配置，改为把平台 `llm_registry` 的实例预置进 `TradingAgentsGraph` 的 `deep_thinking_llm` / `quick_thinking_llm`（pydantic 的 `@computed_field @cached_property`）。本任务把这个机制固化为回归测试——它若失效，必须立刻炸，而不是静默退回 TradingAgents 自建的 LLM 偷用另一套密钥。

**Files:**
- Create: `tests/services/trading_desk/__init__.py`
- Create: `tests/services/trading_desk/test_llm_injection.py`

- [ ] **Step 1: 创建测试包目录**

```bash
mkdir -p tests/services/trading_desk
touch tests/services/trading_desk/__init__.py
```

- [ ] **Step 2: 写测试**

创建 `tests/services/trading_desk/test_llm_injection.py`：

```python
"""验证可以把平台 llm_registry 的实例注入 TradingAgentsGraph。

TradingAgents 默认用自己的 build_chat_model() 造 LLM，会绕开平台的注册表、
密钥管理、token 上限与温度设置。我们改为预置 __dict__ 抢占它的
cached_property。这个机制依赖它的内部实现，本测试是回归防线：
升级 tradingagents 版本后若此测试失败，说明注入已失效，绝不能忽略。
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

from tradingagents import TradingAgentsConfig, TradingAgentsGraph


def _config(tmp_path: Path) -> TradingAgentsConfig:
    """构造一份最小可用配置。这 6 个字段在 TradingAgentsConfig 中是必填的。"""
    return TradingAgentsConfig(
        results_dir=tmp_path,           # data_cache_dir 是它的只读 property，派生自 results_dir
        llm_provider="openai",          # 注入生效后此字段不再被消费，仅作日志元数据
        deep_think_llm="platform-deep",
        quick_think_llm="platform-quick",
        response_language="zh-CN",
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        max_recur_limit=30,             # 字段带 ge=30 约束，不可更小
    )


def test_injected_llms_preempt_internal_construction(tmp_path: Path) -> None:
    """预置 __dict__ 后，读取到的是我们注入的实例，且 _create_llm 从未被调用。"""
    graph = TradingAgentsGraph(config=_config(tmp_path))

    calls: list[str] = []
    graph._create_llm = lambda model: calls.append(model)  # type: ignore[method-assign]

    deep = GenericFakeChatModel(messages=iter(["deep"]))
    quick = GenericFakeChatModel(messages=iter(["quick"]))
    graph.__dict__["deep_thinking_llm"] = deep
    graph.__dict__["quick_thinking_llm"] = quick

    assert graph.deep_thinking_llm is deep
    assert graph.quick_thinking_llm is quick
    assert calls == [], "注入失效：TradingAgents 自建了 LLM，会绕开平台密钥与配置"


def test_without_injection_internal_construction_is_used(tmp_path: Path) -> None:
    """反向对照：不注入时它会走自己的 _create_llm。

    这条断言保证上一个测试不是因为 _create_llm 本来就不被调用而假通过。
    """
    graph = TradingAgentsGraph(config=_config(tmp_path))

    calls: list[str] = []
    graph._create_llm = lambda model: calls.append(model) or GenericFakeChatModel(  # type: ignore[method-assign]
        messages=iter(["x"])
    )

    _ = graph.deep_thinking_llm
    _ = graph.quick_thinking_llm

    assert calls == ["platform-deep", "platform-quick"]
```

- [ ] **Step 3: 运行测试**

```bash
uv run pytest tests/services/trading_desk/test_llm_injection.py -v
```

预期：两个测试全部 PASS。

若 `test_injected_llms_preempt_internal_construction` 失败（`calls` 非空），说明 pydantic 的 `cached_property` 语义或属性名已变——**停止**，回到 spec §7.4 重新设计注入方式，不要往下做。

- [ ] **Step 4: 提交**

```bash
git add tests/services/trading_desk/
git commit -m "test(trading-desk): 固化 LLM 实例注入机制的回归防线"
```

---

## Task 3: HITL 注入前置验证（阶段 0 硬门槛）

Spec §5.3：TradingAgents 的 `AgentState` 没有给人类留位置，`situation_summary` 只用于 BM25 记忆检索、不进 prompt。人工意见必须嫁接到下游节点真正读取的 report 字段上。

**这一步不通过就必须停止整个项目并回到设计层重找嫁接点**——后面所有 HITL 相关的工作都建立在它成立之上。

**Files:**
- Create: `tests/services/trading_desk/test_hitl_injection_probe.py`

- [ ] **Step 1: 写探针测试**

创建 `tests/services/trading_desk/test_hitl_injection_probe.py`：

```python
"""HITL 注入的可行性探针（spec §5.3 的阶段 0 硬门槛）。

验证链路：
  1. 取 TradingAgents 已编译图的 .builder，重新编译并挂上 checkpointer
     与 interrupt_before —— 它自己是裸 compile()，没有中断能力
  2. 跑到 Bull Researcher 之前中断
  3. 用 aupdate_state 把人工意见追加进 news_report
  4. 恢复执行
  5. 断言人工意见确实出现在 Bull Researcher 的最终 prompt 里

第 5 步是关键：写进 situation_summary 是个陷阱（只影响记忆检索），
本测试确保我们嫁接到了真正会进 prompt 的字段。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import Field

from tradingagents import TradingAgentsConfig, TradingAgentsGraph

HUMAN_NOTE = "【人工补充意见】把出口管制风险的权重调高，这是本轮必须纳入的约束。"

AGENT_NODES = [
    "Market Analyst",
    "Social Analyst",
    "News Analyst",
    "Fundamentals Analyst",
    "Situation Summariser",
    "Bull Researcher",
    "Bear Researcher",
    "Research Manager",
    "Trader",
    "Aggressive Analyst",
    "Neutral Analyst",
    "Conservative Analyst",
    "Risk Judge",
]


class RecordingFakeLLM(BaseChatModel):
    """记录每次调用收到的完整 prompt，并返回固定回复。不联网、不花钱。"""

    prompts: list[str] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "recording-fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.prompts.append("\n".join(str(m.content) for m in messages))
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="测试用固定回复。"))]
        )

    def bind_tools(self, tools: Any, **kwargs: Any) -> "RecordingFakeLLM":
        """分析师节点会绑定工具；返回自身即可，固定回复不含 tool_calls。"""
        return self


@pytest.mark.asyncio
async def test_human_note_reaches_bull_researcher_prompt(tmp_path: Path) -> None:
    config = TradingAgentsConfig(
        results_dir=tmp_path,
        llm_provider="openai",
        deep_think_llm="fake-deep",
        quick_think_llm="fake-quick",
        response_language="zh-CN",
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        max_recur_limit=30,
    )
    ta = TradingAgentsGraph(config=config)

    fake = RecordingFakeLLM()
    ta.__dict__["deep_thinking_llm"] = fake
    ta.__dict__["quick_thinking_llm"] = fake

    # 重编译：它自己是裸 compile()，没有 checkpointer 也没有中断点
    compiled = ta.graph.builder.compile(
        checkpointer=InMemorySaver(),
        interrupt_before=AGENT_NODES,
    )

    cfg = {"configurable": {"thread_id": "probe-1"}, "recursion_limit": 100}
    init = ta.propagator.create_initial_state("NVDA", "2026-08-30")

    # 一路自动恢复，直到停在 Bull Researcher 之前
    async for _ in compiled.astream(init, cfg, stream_mode="updates"):
        pass
    state = await compiled.aget_state(cfg)
    while state.next and state.next[0] != "Bull Researcher":
        async for _ in compiled.astream(None, cfg, stream_mode="updates"):
            pass
        state = await compiled.aget_state(cfg)

    assert state.next == ("Bull Researcher",), f"未停在预期节点，实际停在 {state.next}"

    # 注入：追加到 news_report 尾部
    current_news = state.values["news_report"] if isinstance(state.values, dict) else state.values.news_report
    await compiled.aupdate_state(cfg, {"news_report": f"{current_news}\n\n---\n{HUMAN_NOTE}"})

    fake.prompts.clear()
    async for _ in compiled.astream(None, cfg, stream_mode="updates"):
        pass

    joined = "\n".join(fake.prompts)
    assert HUMAN_NOTE in joined, (
        "人工意见没有进入下游 prompt —— news_report 不是有效的嫁接点，"
        "必须停下来回到 spec §5.3 重新选字段"
    )
```

- [ ] **Step 2: 运行探针**

```bash
uv run pytest tests/services/trading_desk/test_hitl_injection_probe.py -v -s
```

预期：PASS。

**若失败，按失败点分别处理，不要绕过：**

- `create_initial_state` 签名不符 → 用 `uv run python -c "import inspect; from tradingagents.graph.propagation import Propagator; print(inspect.signature(Propagator.create_initial_state))"` 查实际签名并修正调用
- 停不到 `Bull Researcher` → 打印 `state.next` 看实际拓扑，核对 `AGENT_NODES` 里的节点名拼写
- 断言 `HUMAN_NOTE in joined` 失败 → **这是硬门槛失败**。停止本计划，回到 spec §5.3，改用 `market_report` / `fundamentals_report` / `sentiment_report` 逐个试；四个都不行则该方案不成立，需重新设计 HITL 机制

- [ ] **Step 3: 提交**

```bash
git add tests/services/trading_desk/test_hitl_injection_probe.py
git commit -m "test(trading-desk): HITL 注入嫁接点的可行性探针"
```

---

## Task 4: 配置项

**Files:**
- Modify: `app/core/config.py`
- Modify: `.env.example`

- [ ] **Step 1: 加配置**

在 `app/core/config.py` 的 `Settings.__init__` 中，紧接 `SUPPLY_CHAIN_*` 那组配置之后加入：

```python
        # ── 交易台（多智能体分析）─────────────────────────────────────
        # LLM 复用平台统一配置：LLM_PROVIDER / *_API_KEY / MAX_TOKENS /
        # DEFAULT_LLM_TEMPERATURE 一律沿用，此处不引入第二套供应商配置。
        # 下面两个是注册表里的「模型名」（非供应商模型 ID），沿用
        # SUPPLY_CHAIN_DISCOVER_MODEL 的先例，留空回落 DEFAULT_LLM_MODEL。
        self.TRADING_DESK_ENGINE = os.getenv("TRADING_DESK_ENGINE", "tradingagents")
        self.TRADING_DESK_DEEP_MODEL = os.getenv("TRADING_DESK_DEEP_MODEL", "")
        self.TRADING_DESK_QUICK_MODEL = os.getenv("TRADING_DESK_QUICK_MODEL", "")
        self.TRADING_DESK_MAX_DEBATE_ROUNDS = int(os.getenv("TRADING_DESK_MAX_DEBATE_ROUNDS", "2"))
        self.TRADING_DESK_MAX_RISK_ROUNDS = int(os.getenv("TRADING_DESK_MAX_RISK_ROUNDS", "1"))
        self.TRADING_DESK_EVENT_TTL_SECONDS = int(os.getenv("TRADING_DESK_EVENT_TTL_SECONDS", "604800"))
```

- [ ] **Step 2: 同步 `.env.example`**

在 `.env.example` 末尾追加：

```bash
# ── 交易台（多智能体分析）────────────────────────────────────────────
# LLM 走平台统一配置（LLM_PROVIDER / *_API_KEY / MAX_TOKENS /
# DEFAULT_LLM_TEMPERATURE），交易台不新增任何供应商或密钥变量。
TRADING_DESK_ENGINE=tradingagents
# 注册表里的模型名，非供应商模型 ID；留空则回落 DEFAULT_LLM_MODEL
TRADING_DESK_DEEP_MODEL=
TRADING_DESK_QUICK_MODEL=
TRADING_DESK_MAX_DEBATE_ROUNDS=2
TRADING_DESK_MAX_RISK_ROUNDS=1
# 事件流在 Redis 中的保留时长，默认 7 天
TRADING_DESK_EVENT_TTL_SECONDS=604800
```

- [ ] **Step 3: 验证配置可读**

```bash
uv run python -c "
from app.core.config import settings
print(settings.TRADING_DESK_ENGINE, settings.TRADING_DESK_MAX_DEBATE_ROUNDS, settings.TRADING_DESK_EVENT_TTL_SECONDS)
"
```

预期输出：`tradingagents 2 604800`

- [ ] **Step 4: 提交**

```bash
git add app/core/config.py .env.example
git commit -m "feat(trading-desk): 新增模块配置项"
```

---

## Task 5: 事件协议 schema

前后端唯一契约。任何引擎都必须把中间输出映射成这里的事件。

**Files:**
- Create: `app/schemas/trading_desk.py`
- Test: `tests/services/trading_desk/test_events.py`

- [ ] **Step 1: 写失败的测试**

创建 `tests/services/trading_desk/test_events.py`：

```python
"""交易台事件协议的形状测试。"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.schemas.trading_desk import (
    EngineCapabilities,
    EventType,
    RunStartedData,
    SignalData,
    StageDescriptor,
    TokenData,
    TradingDeskEvent,
    VerdictData,
)


def test_event_envelope_serialises_to_flat_json() -> None:
    ev = TradingDeskEvent.of(
        run_id="r1",
        type_=EventType.AGENT_TOKEN,
        payload=TokenData(turn_id="t1", text="片段"),
    )
    payload = json.loads(ev.model_dump_json())

    assert payload["type"] == "agent.token"
    assert payload["run_id"] == "r1"
    assert payload["seq"] == 0
    assert payload["data"] == {"turn_id": "t1", "text": "片段"}
    assert isinstance(payload["ts"], int)


def test_run_started_carries_engine_topology() -> None:
    data = RunStartedData(
        ticker="NVDA",
        trade_date="2026-08-30",
        engine="mock/1",
        capabilities=EngineCapabilities(supports_pause=True, supports_inject=True),
        stages=[StageDescriptor(id="s1", name="基本面分析师", role="价值", group="analyst")],
    )
    ev = TradingDeskEvent.of(run_id="r1", type_=EventType.RUN_STARTED, payload=data)

    assert ev.data["stages"][0]["group"] == "analyst"
    assert ev.data["capabilities"]["supports_resume_after_restart"] is False


def test_signal_confidence_is_bounded() -> None:
    with pytest.raises(ValidationError):
        SignalData(stage_id="s1", name="技术面", dir="bull", conf=101)


def test_verdict_matches_trade_recommendation_shape() -> None:
    v = VerdictData(signal="BUY", confidence=0.66, size_fraction=0.04, rationale="理由")

    assert v.warning_message is None
    assert v.target_price is None
    assert v.currency is None


def test_event_can_round_trip() -> None:
    ev = TradingDeskEvent.of(run_id="r1", type_=EventType.STAGE_DONE)
    restored = TradingDeskEvent.model_validate_json(ev.model_dump_json())

    assert restored.type is EventType.STAGE_DONE
    assert restored.data == {}
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/services/trading_desk/test_events.py -q
```

预期：FAIL，`ModuleNotFoundError: No module named 'app.schemas.trading_desk'`

- [ ] **Step 3: 实现 schema**

创建 `app/schemas/trading_desk.py`：

```python
"""交易台事件协议 —— 前后端唯一契约。

任何引擎（TradingAgents / 未来的 ai-hedge-fund）都必须把自己的中间输出
映射成这里定义的事件；前端只认这套 schema。这层抽象是「前端壳可复用、
后端引擎可替换」的关键，改动需同步 frontend/lib/api/trading_desk.ts。

设计要点：
  - agent.token 是增量，前端按 turn_id 累加（不是 stage_id：一个辩论
    stage 会产生多张卡片，按 stage 累加会串台）
  - debate.turn 的 polarity 让前端无需认识具体门派即可决定配色与分栏，
    因此同一套渲染既能画多空二元辩论，也能画激进/中立/保守三方辩论
"""

from __future__ import annotations

import time
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.base import BaseResponse

Polarity = Literal["bull", "bear", "neutral"]
StageGroup = Literal["analyst", "system", "debate", "manager", "trader"]


class EventType(StrEnum):
    """事件类型。值即 SSE 载荷里的 type 字段。"""

    RUN_STARTED = "run.started"
    STAGE_ACTIVE = "stage.active"
    STAGE_DONE = "stage.done"
    TURN_STARTED = "turn.started"
    AGENT_TOOL_CALL = "agent.tool_call"
    AGENT_TOKEN = "agent.token"
    TURN_DONE = "turn.done"
    AGENT_SIGNAL = "agent.signal"
    DEBATE_TURN = "debate.turn"
    HUMAN_NOTE = "human.note"
    CONSENSUS_UPDATE = "consensus.update"
    RUN_PAUSED = "run.paused"
    RUN_RESUMED = "run.resumed"
    VERDICT = "verdict"
    RUN_FINISHED = "run.finished"
    ERROR = "error"


class EngineCapabilities(BaseModel):
    """引擎能力声明。前端据此决定「暂停」「注入意见」按钮是否可用——
    做不到的引擎让按钮置灰，而不是点了没反应。"""

    supports_pause: bool = False
    supports_inject: bool = False
    supports_resume_after_restart: bool = False


class StageDescriptor(BaseModel):
    """流程条上的一个节点。由引擎自报，前端不写死。"""

    id: str
    name: str
    role: str = ""
    group: StageGroup = "analyst"


class EngineDescriptor(BaseModel):
    """引擎自我描述，用于填充 run.started。"""

    engine: str
    capabilities: EngineCapabilities
    stages: list[StageDescriptor]


# ── 各事件的 data 载荷 ──────────────────────────────────────────────


class RunStartedData(BaseModel):
    ticker: str
    trade_date: str
    engine: str
    capabilities: EngineCapabilities
    stages: list[StageDescriptor]


class StageData(BaseModel):
    stage_id: str


class TurnStartedData(BaseModel):
    turn_id: str
    stage_id: str
    name: str
    role: str = ""
    avatar: str = ""


class ToolCallData(BaseModel):
    turn_id: str
    tool: str
    args: dict[str, Any] | None = None


class TokenData(BaseModel):
    turn_id: str
    text: str


class TurnDoneData(BaseModel):
    turn_id: str


class SignalData(BaseModel):
    stage_id: str
    name: str
    dir: Polarity
    conf: int = Field(ge=0, le=100)
    turn_id: str | None = None
    # 引擎原生产出为 False；由我们抽取而来为 True（TradingAgents 的分析师
    # 不产出结构化信号，靠 signal_extract 补齐——前端要能区分展示）
    extracted: bool = False


class DebateTurnData(BaseModel):
    stage_id: str
    debate_id: str
    side: str
    side_label: str
    polarity: Polarity
    round: int
    turn_id: str


class HumanNoteData(BaseModel):
    text: str
    # 写进了引擎状态的哪个字段，便于审计与排障
    injected_into: str | None = None


class ConsensusData(BaseModel):
    bull: int
    neutral: int
    bear: int
    lean: str


class PauseData(BaseModel):
    at_stage_id: str | None = None


class VerdictData(BaseModel):
    """对齐 TradingAgents 的 TradeRecommendation。

    warning_message 由引擎在 JSON 解析失败走 fallback 时置位，
    必须在裁决卡上显式展示，不能吞——否则用户会把降级解析出的结论
    当作正常结论。
    """

    signal: Literal["BUY", "SELL", "HOLD"]
    confidence: float = Field(ge=0.0, le=1.0)
    size_fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    entry_reference_price: float | None = None
    target_price: float | None = None
    stop_loss: float | None = None
    currency: str | None = None
    time_horizon_days: int | None = None
    rationale: str = ""
    warning_message: str | None = None


class RunFinishedData(BaseModel):
    status: Literal["completed", "cancelled", "failed", "interrupted"]
    duration_ms: int = 0


class ErrorData(BaseModel):
    message: str
    stage_id: str | None = None
    fatal: bool = False


# ── 信封 ────────────────────────────────────────────────────────────


class TradingDeskEvent(BaseModel):
    """SSE 事件信封。

    seq 由 event_bus 在写入时填充（Redis 单调计数器），前端用于去重；
    SSE 的 id 字段则用 Redis Stream ID，供 Last-Event-ID 断线续读。
    """

    type: EventType
    run_id: str
    seq: int = 0
    ts: int = Field(default_factory=lambda: int(time.time() * 1000))
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def of(
        cls,
        run_id: str,
        type_: EventType,
        payload: BaseModel | None = None,
    ) -> "TradingDeskEvent":
        """由类型化载荷构造事件。载荷统一序列化为 JSON 兼容的 dict。"""
        return cls(
            type=type_,
            run_id=run_id,
            data=payload.model_dump(mode="json") if payload is not None else {},
        )

    def is_terminal(self) -> bool:
        """是否为终止事件。event_bus 的订阅者据此结束循环。"""
        return self.type is EventType.RUN_FINISHED or (
            self.type is EventType.ERROR and bool(self.data.get("fatal"))
        )


# ── 请求 / 响应 ─────────────────────────────────────────────────────


class CreateRunRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    trade_date: str | None = None  # 留空则用今天（UTC）


class CreateRunResponse(BaseResponse):
    run_id: str


class ControlAction(StrEnum):
    PAUSE = "pause"
    RESUME = "resume"
    INJECT = "inject"
    CANCEL = "cancel"


class ControlRequest(BaseModel):
    action: ControlAction
    text: str | None = None  # action=inject 时必填


class ControlResponse(BaseResponse):
    accepted: bool
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/services/trading_desk/test_events.py -v
```

预期：5 个测试全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add app/schemas/trading_desk.py tests/services/trading_desk/test_events.py
git commit -m "feat(trading-desk): 事件协议 schema"
```

---

## Task 6: 引擎接口

**Files:**
- Create: `app/services/trading_desk/__init__.py`
- Create: `app/services/trading_desk/engine_base.py`
- Create: `app/services/trading_desk/engines/__init__.py`

- [ ] **Step 1: 创建包目录**

```bash
mkdir -p app/services/trading_desk/engines
touch app/services/trading_desk/__init__.py app/services/trading_desk/engines/__init__.py
```

- [ ] **Step 2: 实现接口**

创建 `app/services/trading_desk/engine_base.py`：

```python
"""交易台引擎接口。

引擎 = 整条流水线：给定标的与人工意见，产出事件异步流。DAG 编排属于
引擎内部，不上浮到本层。这是「用它而不抄它」唯一自洽的切法——若把流程
固定成我们自己的 DAG，就必须把 TradingAgents 拆开重组（等于抄了一半），
还会丢掉它的三方风控辩论。换引擎只需再写一个实现，事件协议与前端壳不动。

代价：不同引擎的流程条长得不一样。这是可接受的——引擎的差异本来就该被看见。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.schemas.trading_desk import EngineDescriptor, TradingDeskEvent


@dataclass(frozen=True)
class ControlHandle:
    """runner 交给引擎的控制句柄，让引擎在节点边界响应人机交互。

    引擎只在自己的节点边界调用这些方法——这样暂停不会把某个 agent 的
    推理拦腰截断。
    """

    is_paused: Callable[[], Awaitable[bool]]
    is_cancelled: Callable[[], Awaitable[bool]]
    drain_notes: Callable[[], Awaitable[list[str]]]


@dataclass(frozen=True)
class RunContext:
    """一次运行的上下文。"""

    run_id: str
    ticker: str
    trade_date: str
    control: ControlHandle


@runtime_checkable
class TradingEngine(Protocol):
    """交易台引擎协议。

    实现者：
      - engines/mock.py         回放固定序列，不调 LLM
      - engines/tradingagents.py 包 TradingAgents（计划三）
    """

    name: str

    def describe(self) -> EngineDescriptor:
        """自报拓扑与能力，用于填充 run.started。"""
        ...

    def astream(self, ctx: RunContext) -> AsyncIterator[TradingDeskEvent]:
        """产出事件异步流。不应产出 run.started / run.finished ——
        这两个由 runner 统一包裹，保证所有引擎的生命周期事件一致。"""
        ...
```

- [ ] **Step 3: 验证类型检查通过**

```bash
uv run ruff check app/services/trading_desk/ && uv run pyright app/services/trading_desk/
```

预期：均无错误。

- [ ] **Step 4: 提交**

```bash
git add app/services/trading_desk/
git commit -m "feat(trading-desk): 引擎接口定义"
```

---

## Task 7: MockEngine

Spec §6：mock 从第一天就是正式引擎实现。它让前端联调、runner/SSE/HITL 的集成测试与 CI 全都不需要真实 LLM，同时是「引擎可替换」抽象的第一个验证者。

**Files:**
- Create: `app/services/trading_desk/engines/mock.py`
- Test: `tests/services/trading_desk/test_mock_engine.py`

- [ ] **Step 1: 写失败的测试**

创建 `tests/services/trading_desk/test_mock_engine.py`：

```python
"""MockEngine 行为测试。"""

from __future__ import annotations

from app.schemas.trading_desk import EventType, TradingDeskEvent
from app.services.trading_desk.engine_base import ControlHandle, RunContext
from app.services.trading_desk.engines.mock import MockEngine


def _ctx(
    *,
    paused_sequence: list[bool] | None = None,
    notes: list[str] | None = None,
    cancelled: bool = False,
) -> RunContext:
    pending_pause = list(paused_sequence or [])
    pending_notes = list(notes or [])

    async def is_paused() -> bool:
        return pending_pause.pop(0) if pending_pause else False

    async def is_cancelled() -> bool:
        return cancelled

    async def drain_notes() -> list[str]:
        drained, pending_notes[:] = list(pending_notes), []
        return drained

    return RunContext(
        run_id="r1",
        ticker="NVDA",
        trade_date="2026-08-30",
        control=ControlHandle(is_paused=is_paused, is_cancelled=is_cancelled, drain_notes=drain_notes),
    )


async def _collect(engine: MockEngine, ctx: RunContext) -> list[TradingDeskEvent]:
    return [ev async for ev in engine.astream(ctx)]


def test_describe_reports_topology_and_capabilities() -> None:
    d = MockEngine().describe()

    assert d.capabilities.supports_pause is True
    assert d.capabilities.supports_inject is True
    assert len(d.stages) >= 6
    assert {s.group for s in d.stages} >= {"analyst", "debate", "manager"}


async def test_stream_emits_tokens_debate_and_verdict() -> None:
    events = await _collect(MockEngine(tick_seconds=0), _ctx())
    types = [e.type for e in events]

    assert EventType.AGENT_TOKEN in types
    assert EventType.DEBATE_TURN in types
    assert EventType.AGENT_SIGNAL in types
    assert types[-1] is EventType.VERDICT, "最后一个事件应为裁决；run.finished 由 runner 包裹"


async def test_every_token_belongs_to_an_opened_turn() -> None:
    events = await _collect(MockEngine(tick_seconds=0), _ctx())

    opened: set[str] = set()
    for ev in events:
        if ev.type is EventType.TURN_STARTED:
            opened.add(ev.data["turn_id"])
        if ev.type is EventType.AGENT_TOKEN:
            assert ev.data["turn_id"] in opened, "token 归属到了未开启的 turn"


async def test_debate_turns_carry_polarity_and_round() -> None:
    events = await _collect(MockEngine(tick_seconds=0), _ctx())
    debates = [e for e in events if e.type is EventType.DEBATE_TURN]

    assert {d.data["polarity"] for d in debates} >= {"bull", "bear"}
    assert max(d.data["round"] for d in debates) >= 2


async def test_injected_note_becomes_human_note_event() -> None:
    events = await _collect(MockEngine(tick_seconds=0), _ctx(notes=["把出口管制风险的权重调高"]))
    notes = [e for e in events if e.type is EventType.HUMAN_NOTE]

    assert len(notes) == 1
    assert notes[0].data["text"] == "把出口管制风险的权重调高"
    assert notes[0].data["injected_into"] == "news_report"


async def test_cancel_stops_the_stream_early() -> None:
    events = await _collect(MockEngine(tick_seconds=0), _ctx(cancelled=True))

    assert all(e.type is not EventType.VERDICT for e in events)
    assert len(events) < 10
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/services/trading_desk/test_mock_engine.py -q
```

预期：FAIL，`ModuleNotFoundError: No module named 'app.services.trading_desk.engines.mock'`

- [ ] **Step 3: 实现 MockEngine**

创建 `app/services/trading_desk/engines/mock.py`：

```python
"""MockEngine —— 回放一段固定的分析剧本，不调用任何 LLM。

用途有三，缺一不可：
  1. 前端联调：没有 LLM 成本与延迟，交互体感可以反复打磨
  2. 集成测试与 CI：runner / event_bus / SSE / HITL 全链路可测
  3. 「引擎可替换」抽象的第一个验证者 —— 它与 TradingAgentsEngine
     共用同一个接口，说明将来接 ai-hedge-fund 也能

剧本内容取自交互原型 docs/floor-prototype-cn.html，仅用于打磨交互，
不构成任何投资观点。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.schemas.trading_desk import (
    ConsensusData,
    DebateTurnData,
    EngineCapabilities,
    EngineDescriptor,
    EventType,
    HumanNoteData,
    Polarity,
    SignalData,
    StageData,
    StageDescriptor,
    TokenData,
    ToolCallData,
    TradingDeskEvent,
    TurnDoneData,
    TurnStartedData,
    VerdictData,
)
from app.services.trading_desk.engine_base import RunContext

_STAGES = [
    StageDescriptor(id="fundamentals", name="基本面分析师", role="价值", group="analyst"),
    StageDescriptor(id="market", name="技术面分析师", role="价格行为", group="analyst"),
    StageDescriptor(id="news", name="消息与情绪", role="资讯流", group="analyst"),
    StageDescriptor(id="research_debate", name="研究员辩论", role="多空对辩", group="debate"),
    StageDescriptor(id="trader", name="交易员", role="综合", group="trader"),
    StageDescriptor(id="risk", name="风控委员会", role="约束", group="debate"),
    StageDescriptor(id="pm", name="投资组合经理", role="裁决", group="manager"),
]


@dataclass(frozen=True)
class _Beat:
    """剧本里的一拍：一个 agent 的一次发言。"""

    stage_id: str
    turn_id: str
    name: str
    role: str
    avatar: str
    text: str
    tools: tuple[str, ...] = ()
    signal: tuple[Polarity, int] | None = None
    debate: tuple[str, str, str, Polarity, int] | None = None  # (debate_id, side, label, polarity, round)


_SCRIPT: tuple[_Beat, ...] = (
    _Beat(
        stage_id="fundamentals", turn_id="fundamentals-1", name="基本面分析师", role="价值", avatar="FA",
        tools=("financials.get", "earnings.get"),
        text=(
            "数据中心营收仍在复合增长，但同比增速已在高基数上放缓。毛利率依旧优秀（约 73%）。"
            "前瞻市盈率约 35 倍，已经把「持续统治」定价进去了——公司质地一流，但安全边际很薄。"
        ),
        signal=("neutral", 55),
    ),
    _Beat(
        stage_id="market", turn_id="market-1", name="技术面分析师", role="价格行为", avatar="TA",
        tools=("ohlcv.get", "indicators.calc"),
        text=(
            "回调后重新站上 50 日均线，更高低点的结构完好。RSI 61，有动能但还没超买。"
            "上涨日成交量配合。下方支撑清晰，前高是头顶的阻力位。"
        ),
        signal=("bull", 64),
    ),
    _Beat(
        stage_id="news", turn_id="news-1", name="消息与情绪", role="资讯流", avatar="NA",
        tools=("news.search", "sentiment.score"),
        text=(
            "消息面喜忧参半：超大规模厂商资本开支指引强劲是顺风，但出口管制的噪音、"
            "以及大客户自研芯片的动作是压制项。近期净情绪：谨慎偏正面。"
        ),
        signal=("bull", 58),
    ),
    _Beat(
        stage_id="research_debate", turn_id="research-r1-bull", name="多头研究员", role="第 1 轮", avatar="BR",
        debate=("research", "bull", "多头研究员", "bull", 1),
        text=(
            "这不是一个季度的故事。前四大云厂商的资本开支承诺是多年期的，当下也没有能规模化"
            "替代的方案。就算从纪录高基数上放缓，那也还是 40%+ 的增速。"
        ),
    ),
    _Beat(
        stage_id="research_debate", turn_id="research-r1-bear", name="空头研究员", role="第 1 轮", avatar="BE",
        debate=("research", "bear", "空头研究员", "bear", 1),
        text=(
            "那正是「一致预期交易」——这本身就是风险，所有人都持有。只要出现一个消化资本开支"
            "的季度、或一个可信的竞争者，在这种估值下就会被狠狠杀跌。集中度风险是实打实的。"
        ),
    ),
    _Beat(
        stage_id="research_debate", turn_id="research-r2-bull", name="多头研究员", role="第 2 轮", avatar="BR",
        debate=("research", "bull", "多头研究员", "bull", 2),
        text=(
            "估值确实贵，我认。但你买的是这场仍处早期的淘金热里唯一的「铲子」。"
            "CUDA 生态的锁定效应被低估了——护城河不只是硅片本身。"
        ),
        signal=("bull", 70),
    ),
    _Beat(
        stage_id="research_debate", turn_id="research-r2-bear", name="空头研究员", role="第 2 轮", avatar="BE",
        debate=("research", "bear", "空头研究员", "bear", 2),
        text=(
            "锁定是真的，但不是永久的——大客户砸钱要绕开的恰恰就是它。我不做空，"
            "我是说：按「一条消息就能跳空 15%」的仓位来管理它。"
        ),
        signal=("bear", 60),
    ),
    _Beat(
        stage_id="trader", turn_id="trader-1", name="交易员", role="综合", avatar="TR",
        text="结论：逻辑成立，但这个估值下入场点很关键。建议先建底仓，回调到支撑再加——现在不上满仓。",
    ),
    _Beat(
        stage_id="risk", turn_id="risk-1", name="风控委员会", role="约束", avatar="RC",
        text=(
            "标记：单一标的集中度，以及约 3 周后财报的事件风险。初始仓位上限 4%，"
            "硬止损 -8%，财报前不加仓。带约束批准。"
        ),
    ),
    _Beat(
        stage_id="pm", turn_id="pm-1", name="投资组合经理", role="最终决策", avatar="PM",
        text=(
            "决策：买入，底仓。需求的持续性 + 技术结构盖过估值风险——"
            "但要在缩小仓位、并锁进风控约束的前提下执行。"
        ),
    ),
)

_VERDICT = VerdictData(
    signal="BUY",
    confidence=0.66,
    size_fraction=0.04,
    entry_reference_price=178.2,
    target_price=205.0,
    stop_loss=163.9,
    currency="USD",
    time_horizon_days=21,
    rationale="多头共识（5 个信号中 3 个偏多）被高估值和事件风险抵消。小仓位入场，回调加仓，财报后重新评估。",
)

# 每次 token 切片的字符数。切得太细会让事件量爆炸，太粗则失去流式观感。
_CHUNK = 6


class MockEngine:
    """回放固定剧本的引擎实现。

    Args:
        tick_seconds: 每个 token 片段之间的间隔。测试传 0 跑满速，
            前端联调传 0.03 左右可获得接近真实的流式观感。
    """

    name = "mock"

    def __init__(self, tick_seconds: float = 0.03) -> None:
        self._tick = tick_seconds

    def describe(self) -> EngineDescriptor:
        return EngineDescriptor(
            engine="mock/1",
            capabilities=EngineCapabilities(
                supports_pause=True,
                supports_inject=True,
                supports_resume_after_restart=False,
            ),
            stages=list(_STAGES),
        )

    async def astream(self, ctx: RunContext) -> AsyncIterator[TradingDeskEvent]:
        run_id = ctx.run_id
        signals: list[tuple[Polarity, int]] = []
        active_stage: str | None = None

        for beat in _SCRIPT:
            # ── 节点边界：先处理取消与暂停，再吐人工意见 ──
            if await ctx.control.is_cancelled():
                return

            while await ctx.control.is_paused():
                if await ctx.control.is_cancelled():
                    return
                await asyncio.sleep(max(self._tick, 0.05))

            for note in await ctx.control.drain_notes():
                yield TradingDeskEvent.of(
                    run_id,
                    EventType.HUMAN_NOTE,
                    HumanNoteData(text=note, injected_into="news_report"),
                )

            if beat.stage_id != active_stage:
                if active_stage is not None:
                    yield TradingDeskEvent.of(run_id, EventType.STAGE_DONE, StageData(stage_id=active_stage))
                active_stage = beat.stage_id
                yield TradingDeskEvent.of(run_id, EventType.STAGE_ACTIVE, StageData(stage_id=active_stage))

            yield TradingDeskEvent.of(
                run_id,
                EventType.TURN_STARTED,
                TurnStartedData(
                    turn_id=beat.turn_id,
                    stage_id=beat.stage_id,
                    name=beat.name,
                    role=beat.role,
                    avatar=beat.avatar,
                ),
            )

            if beat.debate is not None:
                debate_id, side, side_label, polarity, rnd = beat.debate
                yield TradingDeskEvent.of(
                    run_id,
                    EventType.DEBATE_TURN,
                    DebateTurnData(
                        stage_id=beat.stage_id,
                        debate_id=debate_id,
                        side=side,
                        side_label=side_label,
                        polarity=polarity,
                        round=rnd,
                        turn_id=beat.turn_id,
                    ),
                )

            for tool in beat.tools:
                yield TradingDeskEvent.of(
                    run_id, EventType.AGENT_TOOL_CALL, ToolCallData(turn_id=beat.turn_id, tool=tool)
                )
                await asyncio.sleep(self._tick)

            for i in range(0, len(beat.text), _CHUNK):
                yield TradingDeskEvent.of(
                    run_id,
                    EventType.AGENT_TOKEN,
                    TokenData(turn_id=beat.turn_id, text=beat.text[i : i + _CHUNK]),
                )
                await asyncio.sleep(self._tick)

            yield TradingDeskEvent.of(run_id, EventType.TURN_DONE, TurnDoneData(turn_id=beat.turn_id))

            if beat.signal is not None:
                direction, conf = beat.signal
                signals.append(beat.signal)
                yield TradingDeskEvent.of(
                    run_id,
                    EventType.AGENT_SIGNAL,
                    SignalData(
                        stage_id=beat.stage_id,
                        turn_id=beat.turn_id,
                        name=beat.name,
                        dir=direction,
                        conf=conf,
                    ),
                )
                yield TradingDeskEvent.of(run_id, EventType.CONSENSUS_UPDATE, _consensus(signals))

        if active_stage is not None:
            yield TradingDeskEvent.of(run_id, EventType.STAGE_DONE, StageData(stage_id=active_stage))

        yield TradingDeskEvent.of(run_id, EventType.VERDICT, _VERDICT)


def _consensus(signals: list[tuple[Polarity, int]]) -> ConsensusData:
    """按方向计数并给出倾向描述。与前端自算保持同一套口径。"""
    bull = sum(1 for d, _ in signals if d == "bull")
    bear = sum(1 for d, _ in signals if d == "bear")
    neutral = sum(1 for d, _ in signals if d == "neutral")
    total = len(signals) or 1

    if bull > bear:
        lean = "明显偏多" if bull >= total * 0.6 else "略偏多"
    elif bear > bull:
        lean = "偏空"
    else:
        lean = "分歧"

    return ConsensusData(bull=bull, neutral=neutral, bear=bear, lean=lean)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/services/trading_desk/test_mock_engine.py -v
```

预期：6 个测试全部 PASS。

- [ ] **Step 5: 确认它满足 TradingEngine 协议**

```bash
uv run python -c "
from app.services.trading_desk.engine_base import TradingEngine
from app.services.trading_desk.engines.mock import MockEngine
assert isinstance(MockEngine(), TradingEngine)
print('MockEngine 满足 TradingEngine 协议')
"
```

预期输出：`MockEngine 满足 TradingEngine 协议`

- [ ] **Step 6: 提交**

```bash
git add app/services/trading_desk/engines/mock.py tests/services/trading_desk/test_mock_engine.py
git commit -m "feat(trading-desk): MockEngine 回放固定剧本"
```

---

## Task 8: Redis 控制位

**Files:**
- Create: `app/cache/trading_desk_cache.py`
- Test: `tests/services/trading_desk/test_control_cache.py`

- [ ] **Step 1: 写失败的测试**

创建 `tests/services/trading_desk/test_control_cache.py`：

```python
"""交易台控制位的 Redis 操作测试。用 fakeredis 兼容的最小内存替身。"""

from __future__ import annotations

from typing import Any

import pytest

from app.cache import trading_desk_cache as tdc


class FakeRedis:
    """只实现本模块用到的命令的内存替身。"""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[bytes, bytes]] = {}
        self.lists: dict[str, list[bytes]] = {}
        self.expires: dict[str, int] = {}

    async def hset(self, key: str, mapping: dict[str, Any]) -> int:
        bucket = self.hashes.setdefault(key, {})
        for k, v in mapping.items():
            bucket[k.encode()] = str(v).encode()
        return len(mapping)

    async def hget(self, key: str, field: str) -> bytes | None:
        return self.hashes.get(key, {}).get(field.encode())

    async def rpush(self, key: str, *values: str) -> int:
        bucket = self.lists.setdefault(key, [])
        bucket.extend(v.encode() for v in values)
        return len(bucket)

    async def lrange(self, key: str, start: int, end: int) -> list[bytes]:
        bucket = self.lists.get(key, [])
        return bucket[start:] if end == -1 else bucket[start : end + 1]

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            removed += int(self.hashes.pop(key, None) is not None)
            removed += int(self.lists.pop(key, None) is not None)
        return removed

    async def expire(self, key: str, ttl: int) -> bool:
        self.expires[key] = ttl
        return True


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


async def test_new_run_is_neither_paused_nor_cancelled(redis: FakeRedis) -> None:
    await tdc.init_control(redis, "r1")

    assert await tdc.is_paused(redis, "r1") is False
    assert await tdc.is_cancelled(redis, "r1") is False


async def test_pause_and_resume_round_trip(redis: FakeRedis) -> None:
    await tdc.init_control(redis, "r1")

    await tdc.set_paused(redis, "r1", True)
    assert await tdc.is_paused(redis, "r1") is True

    await tdc.set_paused(redis, "r1", False)
    assert await tdc.is_paused(redis, "r1") is False


async def test_cancel_is_sticky(redis: FakeRedis) -> None:
    await tdc.init_control(redis, "r1")
    await tdc.set_cancelled(redis, "r1")

    assert await tdc.is_cancelled(redis, "r1") is True


async def test_drain_notes_returns_and_clears(redis: FakeRedis) -> None:
    await tdc.init_control(redis, "r1")
    await tdc.push_note(redis, "r1", "第一条")
    await tdc.push_note(redis, "r1", "第二条")

    assert await tdc.drain_notes(redis, "r1") == ["第一条", "第二条"]
    assert await tdc.drain_notes(redis, "r1") == []


async def test_control_keys_carry_ttl(redis: FakeRedis) -> None:
    await tdc.init_control(redis, "r1")
    await tdc.push_note(redis, "r1", "x")

    assert redis.expires[tdc.control_key("r1")] > 0
    assert redis.expires[tdc.notes_key("r1")] > 0


async def test_unknown_run_degrades_safely(redis: FakeRedis) -> None:
    """未初始化的 run 不应抛异常——引擎轮询时遇到脏数据要能继续跑完。"""
    assert await tdc.is_paused(redis, "missing") is False
    assert await tdc.is_cancelled(redis, "missing") is False
    assert await tdc.drain_notes(redis, "missing") == []
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/services/trading_desk/test_control_cache.py -q
```

预期：FAIL，`ImportError: cannot import name 'trading_desk_cache'`

- [ ] **Step 3: 实现**

创建 `app/cache/trading_desk_cache.py`：

```python
"""交易台运行控制位的 Redis 操作。

key 格式（项目规则：所有 key 必须有 TTL，严禁永不过期）：
  td:ctl:{run_id}    hash  —— paused / cancelled 标志
  td:notes:{run_id}  list  —— 待注入的人工意见队列
  td:seq:{run_id}    string—— 事件单调序号（由 event_bus 使用）
  td:events:{run_id} stream—— 事件流（由 event_bus 使用）

TTL 统一取 settings.TRADING_DESK_EVENT_TTL_SECONDS，与事件流保持一致：
控制位比事件流活得久没有意义，反之会导致运行中途失去控制。
"""

from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import settings


def control_key(run_id: str) -> str:
    return f"td:ctl:{run_id}"


def notes_key(run_id: str) -> str:
    return f"td:notes:{run_id}"


def _ttl() -> int:
    return settings.TRADING_DESK_EVENT_TTL_SECONDS


async def init_control(redis: Redis, run_id: str) -> None:
    """初始化控制位。运行创建时调用一次。"""
    key = control_key(run_id)
    await redis.hset(key, mapping={"paused": "0", "cancelled": "0"})
    await redis.expire(key, _ttl())


async def set_paused(redis: Redis, run_id: str, paused: bool) -> None:
    key = control_key(run_id)
    await redis.hset(key, mapping={"paused": "1" if paused else "0"})
    await redis.expire(key, _ttl())


async def is_paused(redis: Redis, run_id: str) -> bool:
    return await redis.hget(control_key(run_id), "paused") == b"1"


async def set_cancelled(redis: Redis, run_id: str) -> None:
    """取消是单向的：一旦取消不可撤回。"""
    key = control_key(run_id)
    await redis.hset(key, mapping={"cancelled": "1"})
    await redis.expire(key, _ttl())


async def is_cancelled(redis: Redis, run_id: str) -> bool:
    return await redis.hget(control_key(run_id), "cancelled") == b"1"


async def push_note(redis: Redis, run_id: str, text: str) -> None:
    """把一条人工意见排入队列，等引擎在下一个节点边界取走。"""
    key = notes_key(run_id)
    await redis.rpush(key, text)
    await redis.expire(key, _ttl())


async def drain_notes(redis: Redis, run_id: str) -> list[str]:
    """取出并清空全部待注入意见。

    读后删而非逐条弹出：引擎在一个节点边界应当一次性看到所有积压意见，
    否则多条意见会被拆散到不同 agent，用户无法预期哪条被谁看到。
    """
    key = notes_key(run_id)
    raw = await redis.lrange(key, 0, -1)
    if not raw:
        return []
    await redis.delete(key)
    return [item.decode() if isinstance(item, bytes) else str(item) for item in raw]


async def clear_control(redis: Redis, run_id: str) -> None:
    """运行结束后清理控制位。事件流保留至 TTL 到期，供断线重连与回看。"""
    await redis.delete(control_key(run_id), notes_key(run_id))
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/services/trading_desk/test_control_cache.py -v
```

预期：6 个测试全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add app/cache/trading_desk_cache.py tests/services/trading_desk/test_control_cache.py
git commit -m "feat(trading-desk): 运行控制位 Redis 操作"
```

---

## Task 9: 事件总线

Redis Stream 承担三件事：实时投递、`Last-Event-ID` 断线续读、事件顺序保证。

**Files:**
- Create: `app/services/trading_desk/event_bus.py`
- Test: `tests/services/trading_desk/test_event_bus.py`

- [ ] **Step 1: 写失败的测试**

创建 `tests/services/trading_desk/test_event_bus.py`：

```python
"""事件总线读写测试。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.schemas.trading_desk import EventType, RunFinishedData, TokenData, TradingDeskEvent
from app.services.trading_desk import event_bus


class FakeStreamRedis:
    """只实现 XADD / XRANGE / INCR / EXPIRE 的内存替身。

    Stream ID 用单调递增的 "{n}-0"，字典序与数值序在测试规模下一致。
    """

    def __init__(self) -> None:
        self.streams: dict[str, list[tuple[str, dict[bytes, bytes]]]] = {}
        self.counters: dict[str, int] = {}
        self.expires: dict[str, int] = {}
        self._next = 1

    async def xadd(self, key: str, fields: dict[str, Any]) -> bytes:
        entry_id = f"{self._next}-0"
        self._next += 1
        encoded = {k.encode(): (v if isinstance(v, bytes) else str(v).encode()) for k, v in fields.items()}
        self.streams.setdefault(key, []).append((entry_id, encoded))
        return entry_id.encode()

    async def xrange(self, key: str, min: str = "-", max: str = "+", count: int | None = None):  # noqa: A002
        entries = self.streams.get(key, [])
        if min not in ("-", "0-0"):
            threshold = int(min.lstrip("(").split("-")[0])
            entries = [e for e in entries if int(e[0].split("-")[0]) > threshold]
        return entries[:count] if count else entries

    async def incr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key: str, ttl: int) -> bool:
        self.expires[key] = ttl
        return True


@pytest.fixture
def redis() -> FakeStreamRedis:
    return FakeStreamRedis()


async def test_publish_assigns_monotonic_seq(redis: FakeStreamRedis) -> None:
    for _ in range(3):
        await event_bus.publish(
            redis, "r1", TradingDeskEvent.of("r1", EventType.AGENT_TOKEN, TokenData(turn_id="t", text="x"))
        )

    entries = await redis.xrange(event_bus.stream_key("r1"))
    seqs = [TradingDeskEvent.model_validate_json(fields[b"e"]).seq for _, fields in entries]

    assert seqs == [1, 2, 3]


async def test_publish_sets_ttl_on_stream(redis: FakeStreamRedis) -> None:
    await event_bus.publish(redis, "r1", TradingDeskEvent.of("r1", EventType.STAGE_DONE))

    assert redis.expires[event_bus.stream_key("r1")] > 0


async def test_subscribe_replays_from_beginning(redis: FakeStreamRedis) -> None:
    await event_bus.publish(redis, "r1", TradingDeskEvent.of("r1", EventType.STAGE_ACTIVE))
    await event_bus.publish(
        redis, "r1", TradingDeskEvent.of("r1", EventType.RUN_FINISHED, RunFinishedData(status="completed"))
    )

    received = [ev async for _, ev in event_bus.subscribe(redis, "r1", poll_interval=0)]

    assert [e.type for e in received] == [EventType.STAGE_ACTIVE, EventType.RUN_FINISHED]


async def test_subscribe_resumes_after_last_event_id(redis: FakeStreamRedis) -> None:
    first_id = await event_bus.publish(redis, "r1", TradingDeskEvent.of("r1", EventType.STAGE_ACTIVE))
    await event_bus.publish(
        redis, "r1", TradingDeskEvent.of("r1", EventType.RUN_FINISHED, RunFinishedData(status="completed"))
    )

    received = [ev async for _, ev in event_bus.subscribe(redis, "r1", last_id=first_id, poll_interval=0)]

    assert [e.type for e in received] == [EventType.RUN_FINISHED]


async def test_subscribe_stops_on_fatal_error(redis: FakeStreamRedis) -> None:
    await event_bus.publish(
        redis,
        "r1",
        TradingDeskEvent(type=EventType.ERROR, run_id="r1", data={"message": "boom", "fatal": True}),
    )

    received = [ev async for _, ev in event_bus.subscribe(redis, "r1", poll_interval=0)]

    assert len(received) == 1
    assert received[0].type is EventType.ERROR


async def test_subscribe_times_out_when_run_never_finishes(redis: FakeStreamRedis) -> None:
    await event_bus.publish(redis, "r1", TradingDeskEvent.of("r1", EventType.STAGE_ACTIVE))

    received = [
        ev async for _, ev in event_bus.subscribe(redis, "r1", poll_interval=0.01, idle_timeout=0.05)
    ]

    assert [e.type for e in received] == [EventType.STAGE_ACTIVE]


async def test_subscribe_picks_up_events_published_later(redis: FakeStreamRedis) -> None:
    async def publish_later() -> None:
        await asyncio.sleep(0.02)
        await event_bus.publish(
            redis, "r1", TradingDeskEvent.of("r1", EventType.RUN_FINISHED, RunFinishedData(status="completed"))
        )

    task = asyncio.create_task(publish_later())
    received = [ev async for _, ev in event_bus.subscribe(redis, "r1", poll_interval=0.01, idle_timeout=1.0)]
    await task

    assert [e.type for e in received] == [EventType.RUN_FINISHED]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/services/trading_desk/test_event_bus.py -q
```

预期：FAIL，`ImportError: cannot import name 'event_bus'`

- [ ] **Step 3: 实现**

创建 `app/services/trading_desk/event_bus.py`：

```python
"""交易台事件总线：Redis Stream 读写。

选 Stream 而非 Pub/Sub 的原因：
  - Stream ID 天然单调，直接充当 SSE 的 Last-Event-ID，断线重连即续读
  - 事件被持久化，刷新页面 / 多标签页可以接回同一个 run
  - Pub/Sub 的消息发出即丢，订阅晚一步就永久错过开头

用 XRANGE 轮询而非 XREAD BLOCK：redis-py 的阻塞读会占住连接池里的连接，
一个长跑的 run 配多个订阅者时容易把池吃干；轮询间隔 50ms 对人眼已足够。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import logger
from app.schemas.trading_desk import TradingDeskEvent

# 订阅端默认参数
_POLL_INTERVAL = 0.05
# 超过这个时长没有任何新事件就断开：防止 runner 崩溃后订阅者永久挂着
_IDLE_TIMEOUT = 300.0
_BATCH = 200


def stream_key(run_id: str) -> str:
    return f"td:events:{run_id}"


def seq_key(run_id: str) -> str:
    return f"td:seq:{run_id}"


async def publish(redis: Redis, run_id: str, event: TradingDeskEvent) -> str:
    """写入一条事件，回填 seq，返回 Redis Stream ID。"""
    event.seq = await redis.incr(seq_key(run_id))
    await redis.expire(seq_key(run_id), settings.TRADING_DESK_EVENT_TTL_SECONDS)

    key = stream_key(run_id)
    raw_id = await redis.xadd(key, {"e": event.model_dump_json()})
    await redis.expire(key, settings.TRADING_DESK_EVENT_TTL_SECONDS)

    return raw_id.decode() if isinstance(raw_id, bytes) else str(raw_id)


async def subscribe(
    redis: Redis,
    run_id: str,
    last_id: str | None = None,
    *,
    poll_interval: float = _POLL_INTERVAL,
    idle_timeout: float = _IDLE_TIMEOUT,
) -> AsyncIterator[tuple[str, TradingDeskEvent]]:
    """从 last_id 之后开始消费事件，直到终止事件或空闲超时。

    Args:
        last_id: 上次收到的 Stream ID（来自 SSE 的 Last-Event-ID）。
            None 表示从头重放。
        poll_interval: 无新事件时的轮询间隔。测试传 0 表示不等待。
        idle_timeout: 连续无新事件多久后放弃。

    Yields:
        (stream_id, event) —— stream_id 用于 SSE 的 id 字段。
    """
    cursor = last_id or "0-0"
    idle = 0.0

    while True:
        entries = await redis.xrange(stream_key(run_id), min=f"({cursor}", max="+", count=_BATCH)

        if not entries:
            if poll_interval <= 0 or idle >= idle_timeout:
                return
            await asyncio.sleep(poll_interval)
            idle += poll_interval
            continue

        idle = 0.0
        for entry_id, fields in entries:
            cursor = entry_id.decode() if isinstance(entry_id, bytes) else str(entry_id)
            raw = fields.get(b"e") or fields.get("e")
            if raw is None:
                logger.warning("trading_desk_event_missing_payload", run_id=run_id, entry_id=cursor)
                continue

            event = TradingDeskEvent.model_validate_json(raw)
            yield cursor, event

            if event.is_terminal():
                return
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/services/trading_desk/test_event_bus.py -v
```

预期：7 个测试全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add app/services/trading_desk/event_bus.py tests/services/trading_desk/test_event_bus.py
git commit -m "feat(trading-desk): Redis Stream 事件总线"
```

---

## Task 10: 运行编排

**Files:**
- Create: `app/services/trading_desk/runner.py`
- Test: `tests/services/trading_desk/test_runner.py`

- [ ] **Step 1: 写失败的测试**

创建 `tests/services/trading_desk/test_runner.py`：

```python
"""runner 生命周期测试：用 MockEngine 跑完整链路，不碰真实 LLM。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from app.schemas.trading_desk import EventType, TradingDeskEvent
from app.services.trading_desk import event_bus, runner
from app.services.trading_desk.engine_base import RunContext
from app.services.trading_desk.engines.mock import MockEngine
from tests.services.trading_desk.test_control_cache import FakeRedis
from tests.services.trading_desk.test_event_bus import FakeStreamRedis


class FakeRedisAll(FakeRedis, FakeStreamRedis):
    """同时具备 hash / list / stream / counter 能力的替身。"""

    def __init__(self) -> None:
        FakeRedis.__init__(self)
        FakeStreamRedis.__init__(self)

    async def delete(self, *keys: str) -> int:
        return await FakeRedis.delete(self, *keys)


class BoomEngine:
    """一开跑就抛异常，用于验证失败路径。"""

    name = "boom"

    def describe(self):
        return MockEngine().describe()

    async def astream(self, ctx: RunContext) -> AsyncIterator[TradingDeskEvent]:
        raise RuntimeError("引擎炸了")
        yield  # pragma: no cover  —— 让本函数成为异步生成器


@pytest.fixture
def redis() -> FakeRedisAll:
    return FakeRedisAll()


async def _drain(redis: FakeRedisAll, run_id: str) -> list[TradingDeskEvent]:
    return [ev async for _, ev in event_bus.subscribe(redis, run_id, poll_interval=0)]


async def test_run_wraps_engine_stream_with_lifecycle_events(redis: FakeRedisAll) -> None:
    run_id = await runner.start_run(redis, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0))
    await runner.wait_for(run_id)

    events = await _drain(redis, run_id)

    assert events[0].type is EventType.RUN_STARTED
    assert events[0].data["ticker"] == "NVDA"
    assert events[0].data["engine"] == "mock/1"
    assert events[-1].type is EventType.RUN_FINISHED
    assert events[-1].data["status"] == "completed"


async def test_verdict_precedes_run_finished(redis: FakeRedisAll) -> None:
    run_id = await runner.start_run(redis, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0))
    await runner.wait_for(run_id)

    types = [e.type for e in await _drain(redis, run_id)]

    assert types.index(EventType.VERDICT) < types.index(EventType.RUN_FINISHED)


async def test_engine_failure_emits_fatal_error_then_finished(redis: FakeRedisAll) -> None:
    run_id = await runner.start_run(redis, ticker="NVDA", trade_date="2026-08-30", engine=BoomEngine())
    await runner.wait_for(run_id)

    events = await _drain(redis, run_id)
    errors = [e for e in events if e.type is EventType.ERROR]

    assert len(errors) == 1
    assert errors[0].data["fatal"] is True
    assert "引擎炸了" in errors[0].data["message"]
    assert events[-1].data["status"] == "failed"


async def test_cancel_ends_run_as_cancelled(redis: FakeRedisAll) -> None:
    run_id = await runner.start_run(
        redis, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0.01)
    )
    await asyncio.sleep(0.05)
    await runner.cancel(redis, run_id)
    await runner.wait_for(run_id)

    events = await _drain(redis, run_id)

    assert events[-1].data["status"] == "cancelled"
    assert all(e.type is not EventType.VERDICT for e in events)


async def test_pause_emits_paused_event_and_resume_continues(redis: FakeRedisAll) -> None:
    run_id = await runner.start_run(
        redis, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0.01)
    )
    await asyncio.sleep(0.05)
    await runner.pause(redis, run_id)
    await asyncio.sleep(0.05)
    await runner.resume(redis, run_id)
    await runner.wait_for(run_id)

    types = [e.type for e in await _drain(redis, run_id)]

    assert EventType.RUN_PAUSED in types
    assert EventType.RUN_RESUMED in types
    assert types[-1] is EventType.RUN_FINISHED


async def test_control_keys_are_cleaned_up_after_run(redis: FakeRedisAll) -> None:
    from app.cache import trading_desk_cache as tdc

    run_id = await runner.start_run(redis, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0))
    await runner.wait_for(run_id)

    assert tdc.control_key(run_id) not in redis.hashes
    # 事件流保留，供断线重连与回看
    assert event_bus.stream_key(run_id) in redis.streams
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/services/trading_desk/test_runner.py -q
```

预期：FAIL，`ImportError: cannot import name 'runner'`

- [ ] **Step 3: 实现**

创建 `app/services/trading_desk/runner.py`：

```python
"""交易台运行编排。

职责边界：
  - runner 负责生命周期（run.started / run.finished / error）与控制信号，
    引擎只负责产出中间事件。这样所有引擎的生命周期语义一致，前端不必
    为每个引擎写特例。
  - 运行跑在后台 asyncio 任务里，HTTP 请求立即返回 run_id；SSE 端点是
    独立的消费者，断开不影响运行。

已知取舍：web 进程重启会中断在跑的 run（spec §11）。研究工具可接受，
且事件流已落 Redis，partial 结果仍可见。
"""

from __future__ import annotations

import asyncio
import time
import uuid

from redis.asyncio import Redis

from app.cache import trading_desk_cache as tdc
from app.core.logging import logger
from app.schemas.trading_desk import (
    ErrorData,
    EventType,
    RunFinishedData,
    RunStartedData,
    TradingDeskEvent,
)
from app.services.trading_desk import event_bus
from app.services.trading_desk.engine_base import ControlHandle, RunContext, TradingEngine

# run_id -> 后台任务。仅用于同进程内的 wait_for / 观测；
# 控制信号一律走 Redis，不依赖这个字典（进程重启后它会空掉）。
_TASKS: dict[str, asyncio.Task[None]] = {}


async def start_run(
    redis: Redis,
    *,
    ticker: str,
    trade_date: str,
    engine: TradingEngine,
) -> str:
    """创建一次运行并立即返回 run_id，实际执行在后台进行。"""
    run_id = uuid.uuid4().hex
    await tdc.init_control(redis, run_id)

    task = asyncio.create_task(_execute(redis, run_id, ticker, trade_date, engine))
    _TASKS[run_id] = task
    task.add_done_callback(lambda _: _TASKS.pop(run_id, None))

    logger.info("trading_desk_run_started", run_id=run_id, ticker=ticker, engine=engine.name)
    return run_id


async def _execute(
    redis: Redis,
    run_id: str,
    ticker: str,
    trade_date: str,
    engine: TradingEngine,
) -> None:
    started_at = time.monotonic()
    descriptor = engine.describe()

    await event_bus.publish(
        redis,
        run_id,
        TradingDeskEvent.of(
            run_id,
            EventType.RUN_STARTED,
            RunStartedData(
                ticker=ticker,
                trade_date=trade_date,
                engine=descriptor.engine,
                capabilities=descriptor.capabilities,
                stages=descriptor.stages,
            ),
        ),
    )

    status: str = "completed"
    # 上一次观察到的暂停态，用于只在翻转时发 run.paused / run.resumed
    was_paused = False

    async def is_paused() -> bool:
        nonlocal was_paused
        paused = await tdc.is_paused(redis, run_id)
        if paused != was_paused:
            was_paused = paused
            await event_bus.publish(
                redis,
                run_id,
                TradingDeskEvent.of(
                    run_id, EventType.RUN_PAUSED if paused else EventType.RUN_RESUMED
                ),
            )
        return paused

    ctx = RunContext(
        run_id=run_id,
        ticker=ticker,
        trade_date=trade_date,
        control=ControlHandle(
            is_paused=is_paused,
            is_cancelled=lambda: tdc.is_cancelled(redis, run_id),
            drain_notes=lambda: tdc.drain_notes(redis, run_id),
        ),
    )

    try:
        async for event in engine.astream(ctx):
            await event_bus.publish(redis, run_id, event)

        if await tdc.is_cancelled(redis, run_id):
            status = "cancelled"
    except asyncio.CancelledError:
        status = "cancelled"
        raise
    except Exception as exc:  # noqa: BLE001 —— 任何引擎异常都要变成前端可见的事件
        status = "failed"
        logger.exception("trading_desk_run_failed", run_id=run_id, ticker=ticker)
        await event_bus.publish(
            redis,
            run_id,
            TradingDeskEvent.of(run_id, EventType.ERROR, ErrorData(message=str(exc), fatal=True)),
        )
    finally:
        await event_bus.publish(
            redis,
            run_id,
            TradingDeskEvent.of(
                run_id,
                EventType.RUN_FINISHED,
                RunFinishedData(
                    status=status,  # type: ignore[arg-type]
                    duration_ms=int((time.monotonic() - started_at) * 1000),
                ),
            ),
        )
        await tdc.clear_control(redis, run_id)
        logger.info("trading_desk_run_finished", run_id=run_id, status=status)


async def pause(redis: Redis, run_id: str) -> None:
    await tdc.set_paused(redis, run_id, True)


async def resume(redis: Redis, run_id: str) -> None:
    await tdc.set_paused(redis, run_id, False)


async def cancel(redis: Redis, run_id: str) -> None:
    """请求取消。引擎在下一个节点边界响应；同时解除暂停，避免卡在暂停循环里。"""
    await tdc.set_cancelled(redis, run_id)
    await tdc.set_paused(redis, run_id, False)


async def inject(redis: Redis, run_id: str, text: str) -> None:
    await tdc.push_note(redis, run_id, text)


async def wait_for(run_id: str) -> None:
    """等待同进程内的运行结束。仅供测试与优雅关闭使用。"""
    task = _TASKS.get(run_id)
    if task is not None:
        await asyncio.gather(task, return_exceptions=True)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/services/trading_desk/test_runner.py -v
```

预期：6 个测试全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add app/services/trading_desk/runner.py tests/services/trading_desk/test_runner.py
git commit -m "feat(trading-desk): 运行编排与生命周期"
```

---

## Task 11: API 路由与 SSE

**Files:**
- Create: `app/api/v1/trading_desk.py`
- Test: `tests/api/test_trading_desk_api.py`

- [ ] **Step 1: 写失败的测试**

先确认现有 API 测试的目录：

```bash
ls tests/api/
```

创建 `tests/api/test_trading_desk_api.py`：

```python
"""交易台 API 端到端测试：用 MockEngine + Redis 替身，不碰真实 LLM 与真实 Redis。"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.auth.dependencies import get_current_user
from app.api.v1.trading_desk import get_engine, router
from app.cache.client import get_redis
from app.services.trading_desk.engines.mock import MockEngine
from tests.services.trading_desk.test_runner import FakeRedisAll


@pytest.fixture
def redis() -> FakeRedisAll:
    return FakeRedisAll()


@pytest.fixture
def app(redis: FakeRedisAll) -> FastAPI:
    application = FastAPI()
    application.include_router(router, prefix="/api/v1/trading-desk")
    application.dependency_overrides[get_redis] = lambda: redis
    application.dependency_overrides[get_current_user] = lambda: object()
    application.dependency_overrides[get_engine] = lambda: MockEngine(tick_seconds=0)
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_create_run_returns_run_id(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/trading-desk/runs", json={"ticker": "NVDA"})

    assert resp.status_code == 200
    assert len(resp.json()["run_id"]) == 32


async def test_create_run_rejects_empty_ticker(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/trading-desk/runs", json={"ticker": ""})

    assert resp.status_code == 422


async def test_stream_delivers_full_event_sequence(client: AsyncClient) -> None:
    run_id = (await client.post("/api/v1/trading-desk/runs", json={"ticker": "NVDA"})).json()["run_id"]

    async with client.stream("GET", f"/api/v1/trading-desk/runs/{run_id}/stream") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join([chunk async for chunk in resp.aiter_text()])

    types = [json.loads(line[6:])["type"] for line in body.splitlines() if line.startswith("data: ")]

    assert types[0] == "run.started"
    assert types[-1] == "run.finished"
    assert "agent.token" in types
    assert "verdict" in types


async def test_stream_emits_sse_ids_for_reconnect(client: AsyncClient) -> None:
    run_id = (await client.post("/api/v1/trading-desk/runs", json={"ticker": "NVDA"})).json()["run_id"]

    async with client.stream("GET", f"/api/v1/trading-desk/runs/{run_id}/stream") as resp:
        body = "".join([chunk async for chunk in resp.aiter_text()])

    id_lines = [line for line in body.splitlines() if line.startswith("id: ")]

    assert len(id_lines) > 1


async def test_inject_requires_text(client: AsyncClient) -> None:
    run_id = (await client.post("/api/v1/trading-desk/runs", json={"ticker": "NVDA"})).json()["run_id"]

    resp = await client.post(f"/api/v1/trading-desk/runs/{run_id}/control", json={"action": "inject"})

    assert resp.status_code == 422


async def test_control_actions_are_accepted(client: AsyncClient) -> None:
    run_id = (await client.post("/api/v1/trading-desk/runs", json={"ticker": "NVDA"})).json()["run_id"]

    for payload in (
        {"action": "pause"},
        {"action": "inject", "text": "把出口管制风险的权重调高"},
        {"action": "resume"},
        {"action": "cancel"},
    ):
        resp = await client.post(f"/api/v1/trading-desk/runs/{run_id}/control", json=payload)
        assert resp.status_code == 200, payload
        assert resp.json()["accepted"] is True
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/api/test_trading_desk_api.py -q
```

预期：FAIL，`ModuleNotFoundError: No module named 'app.api.v1.trading_desk'`

- [ ] **Step 3: 实现路由**

创建 `app/api/v1/trading_desk.py`：

```python
"""交易台路由。

本层只做请求解析、参数校验、调用 service、返回响应（项目分层规则）。

SSE 说明：事件从 Redis Stream 消费，每条同时写 SSE 的 id 字段（Redis
Stream ID）。前端断线重连时把它放进 Last-Event-ID 请求头即可续读，
不会漏事件也不会重复。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis

from app.api.v1.auth.dependencies import get_current_user
from app.cache.client import get_redis
from app.core.config import settings
from app.core.logging import logger
from app.models.user import User
from app.schemas.trading_desk import (
    ControlAction,
    ControlRequest,
    ControlResponse,
    CreateRunRequest,
    CreateRunResponse,
)
from app.services.trading_desk import event_bus, runner
from app.services.trading_desk.engine_base import TradingEngine
from app.services.trading_desk.engines.mock import MockEngine

router = APIRouter()


def get_engine() -> TradingEngine:
    """按配置选择引擎。

    第一期只注册 MockEngine；TradingAgentsEngine 在计划三接入。
    做成依赖注入是为了让测试可以覆盖，也让换引擎不必改端点代码。
    """
    if settings.TRADING_DESK_ENGINE == "mock":
        return MockEngine()
    # 计划三接入 TradingAgentsEngine 后，这里按 settings.TRADING_DESK_ENGINE 分支
    return MockEngine()


@router.post("/runs", response_model=CreateRunResponse)
async def create_run(
    payload: CreateRunRequest,
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[Redis, Depends(get_redis)],
    engine: Annotated[TradingEngine, Depends(get_engine)],
) -> CreateRunResponse:
    """创建一次分析运行，立即返回 run_id；实际执行在后台进行。"""
    trade_date = payload.trade_date or datetime.now(UTC).strftime("%Y-%m-%d")
    run_id = await runner.start_run(
        redis,
        ticker=payload.ticker.strip().upper(),
        trade_date=trade_date,
        engine=engine,
    )
    return CreateRunResponse(run_id=run_id)


@router.get("/runs/{run_id}/stream")
async def stream_run(
    run_id: str,
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[Redis, Depends(get_redis)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """以 SSE 推送事件流，支持 Last-Event-ID 断线续读。"""

    async def event_generator():
        try:
            async for stream_id, event in event_bus.subscribe(redis, run_id, last_id=last_event_id):
                yield f"id: {stream_id}\ndata: {event.model_dump_json()}\n\n"
        except Exception:
            logger.exception("trading_desk_stream_failed", run_id=run_id)
            raise

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/runs/{run_id}/control", response_model=ControlResponse)
async def control_run(
    run_id: str,
    payload: ControlRequest,
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> ControlResponse:
    """暂停 / 恢复 / 注入人工意见 / 取消。引擎在下一个节点边界响应。"""
    if payload.action is ControlAction.INJECT and not (payload.text or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="注入意见时 text 不能为空",
        )

    match payload.action:
        case ControlAction.PAUSE:
            await runner.pause(redis, run_id)
        case ControlAction.RESUME:
            await runner.resume(redis, run_id)
        case ControlAction.CANCEL:
            await runner.cancel(redis, run_id)
        case ControlAction.INJECT:
            await runner.inject(redis, run_id, (payload.text or "").strip())

    return ControlResponse(accepted=True)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/api/test_trading_desk_api.py -v
```

预期：6 个测试全部 PASS。

若 `test_inject_requires_text` 返回 200 而非 422，检查 `HTTPException` 的 status_code 是否写对。

- [ ] **Step 5: 提交**

```bash
git add app/api/v1/trading_desk.py tests/api/test_trading_desk_api.py
git commit -m "feat(trading-desk): 运行、SSE 与控制端点"
```

---

## Task 12: 注册路由并验收

**Files:**
- Modify: `app/api/v1/api.py`

- [ ] **Step 1: 注册子路由**

在 `app/api/v1/api.py` 中，import 区按字母序在 `from app.api.v1.transcripts import ...` 之前加入：

```python
from app.api.v1.trading_desk import router as trading_desk_router
```

在 `include_router` 区按字母序在 `transcripts_router` 之前加入：

```python
api_router.include_router(trading_desk_router, prefix="/trading-desk", tags=["trading-desk"])
```

- [ ] **Step 2: 确认应用能启动且路由已挂载**

```bash
uv run python -c "
from app.main import app
paths = sorted(r.path for r in app.routes if 'trading-desk' in getattr(r, 'path', ''))
print('\n'.join(paths))
"
```

预期输出三条：

```
/api/v1/trading-desk/runs
/api/v1/trading-desk/runs/{run_id}/control
/api/v1/trading-desk/runs/{run_id}/stream
```

- [ ] **Step 3: 跑全量测试**

```bash
uv run pytest -m "not slow" -q
```

预期：全部通过，无新增失败。

- [ ] **Step 4: 代码检查**

```bash
make check
```

预期：`ruff check .` 与 `pyright` 均无错误。

- [ ] **Step 5: 真实环境冒烟（需本地 Redis）**

```bash
cd infra && docker compose up -d postgres redis && cd ..
make dev
```

另开一个终端，先拿到登录 token（用你本地的测试账号），然后：

```bash
TOKEN=<你的 access_token>
RUN_ID=$(curl -s -X POST http://localhost:8000/api/v1/trading-desk/runs \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"ticker":"NVDA"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['run_id'])")
echo "run_id=$RUN_ID"

curl -N -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/trading-desk/runs/$RUN_ID/stream"
```

预期：终端里逐条滚出 SSE 事件，从 `run.started` 开始，中间是逐字的 `agent.token`，含 `debate.turn` 与 `agent.signal`，最后是 `verdict` 与 `run.finished`。

再开一个终端测 HITL（趁运行还在跑时）：

```bash
curl -s -X POST "http://localhost:8000/api/v1/trading-desk/runs/$RUN_ID/control" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"action":"pause"}'
```

预期：SSE 流出现 `run.paused` 后停止吐新事件。

```bash
curl -s -X POST "http://localhost:8000/api/v1/trading-desk/runs/$RUN_ID/control" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"action":"inject","text":"把出口管制风险的权重调高"}'

curl -s -X POST "http://localhost:8000/api/v1/trading-desk/runs/$RUN_ID/control" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"action":"resume"}'
```

预期：SSE 流出现 `run.resumed`，紧接着出现一条 `human.note`（内容为注入的文本），然后继续正常推进到 `verdict`。

- [ ] **Step 6: 提交**

```bash
git add app/api/v1/api.py
git commit -m "feat(trading-desk): 注册交易台路由"
```

---

## 验收标准

本计划完成时应满足：

1. `uv run pytest -m "not slow"` 全绿，其中 `tests/services/trading_desk/` 与 `tests/api/test_trading_desk_api.py` 覆盖事件协议、MockEngine、控制位、事件总线、runner 生命周期、API 与 SSE
2. `make check` 无错误
3. Task 12 Step 5 的冒烟脚本能跑出完整事件流，且暂停 / 注入 / 恢复行为符合预期
4. Task 2 与 Task 3 的两个探针测试通过——这是后续接真实引擎的前提

## 下一步

本计划落地后再写：

- **计划二**：前端交易台（spec 阶段 2），接本计划的 SSE 端点与 MockEngine
- **计划三**：TradingAgentsEngine + 信号抽取 + 落库回放（spec 阶段 3-4）
