# 交易台引擎与落库 实施计划（计划三 / 共三）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 TradingAgents 真实引擎接入交易台（token 流 / 辩论 / 裁决 / HITL 全部真实化），并落地运行落库与历史回放。

**Architecture:** `TradingAgentsEngine` 包装 tradingagents 0.7.0 的 LangGraph 图：重编译挂 checkpointer + `interrupt_before`（HITL 骨架），`astream(stream_mode=["messages","updates"])` 双模式取流，翻译器把 LangGraph chunk 映射成事件协议。落库走「runner 收尾时从 Redis Stream 折叠成 turns 存 Postgres」。

**Tech Stack:** Python 3.13 / uv / tradingagents 0.7.0（LangGraph）/ FastAPI / SQLModel + Alembic / llm_registry / pytest

**Spec:** `docs/superpowers/specs/2026-08-30-trading-desk-design.md`（阶段 3-4）
**依赖:** 计划一（接口/runner/event_bus）、计划二（前端壳）均已上线

---

## 前置侦察结论（已实跑验证，写代码时直接依据）

用假 LLM 跑通全图后确认的流结构（`stream_mode=["messages","updates"]` 联合模式，chunk 是 `(mode, payload)` 元组）：

**messages 模式**（`payload = (message, metadata)`）：
- 每条 LLM 输出带 `metadata["langgraph_node"]`，精确到节点名
- `tools_*` 节点的 ToolMessage 是工具结果、`Msg Clear *` 的 HumanMessage `'Continue'` 是管道消息——**都要过滤**，不进推理流
- `AIMessageChunk.tool_call_chunks` 非空时是工具调用，映射 `agent.tool_call`

**updates 模式**（`payload = {node: state_update}`），节点完成时的 state key 就是事件边界：

| 节点 | 完成时的 keys | 对应动作 |
|---|---|---|
| Market/Social/News/Fundamentals Analyst | `messages` + `market_report`/`sentiment_report`/`news_report`/`fundamentals_report` | stage.done + 信号抽取 |
| Situation Summariser | `situation_summary` | stage.done（system 组） |
| Bull/Bear Researcher | `investment_debate_state` | debate.turn 收尾 |
| Research Manager | `investment_debate_state`, `investment_plan` | stage.done |
| Trader | `messages`, `trader_investment_plan` | stage.done |
| Aggressive/Conservative/Neutral Analyst | `risk_debate_state` | debate.turn 收尾 |
| Risk Judge | `risk_debate_state`, `final_trade_decision` | verdict |

**真实拓扑是串行的**：Market → Social → News → Fundamentals → Summariser → Bull → Bear → Research Manager → Trader → **Aggressive → Conservative → Neutral**（注意 C 在 N 前）→ Risk Judge。

**辩论文本**：Bull/Bear 的发言在 `investment_debate_state.current_response`（带 `"Bull Analyst: "` 前缀，渲染前剥掉）。轮次由节点执行次数推得。

**裁决**：`final_trade_decision` 是原始文本，`ta.process_signal(text)` 解析成 `TradeRecommendation`（BUY/SELL/HOLD + confidence + size + rationale + warning_message），**不再需要我们写解析器**。`_enrich_recommendation` 会调 yfinance 取收盘价——跳过（可空字段，前端已兼容）。

**注入点**（计划一探针已验证）：交易员前注入 `news_report` 尾部、交易员后注入 `trader_investment_plan` 尾部。

**LLM 注入**（计划一探针已验证）：`ta.__dict__["deep_thinking_llm"] = ...` 抢占 cached_property，绕开它自带的 `build_chat_model`。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `app/services/trading_desk/engines/stage_map.py` | LangGraph 节点名 ↔ stage/turn 描述符、辩论元数据、过滤规则 |
| `app/services/trading_desk/engines/tradingagents.py` | TradingAgentsEngine：图构建、LLM 注入、双模式流翻译、HITL 循环 |
| `app/services/trading_desk/signal_extract.py` | 从 report 文本抽 {dir, conf}（quick model，失败降级 neutral） |
| `app/models/trading_desk_run.py` | TradingDeskRun 表模型 |
| `app/services/trading_desk/persistence.py` | 从 Redis Stream 折叠事件 → 落库 |
| `app/api/v1/trading_desk.py` | 追加 GET /runs、GET /runs/{id}；get_engine 接真实引擎 |
| `app/schemas/trading_desk.py` | 追加历史/详情响应 schema |
| `frontend/lib/api/trading_desk.ts` | 追加历史 API |
| `frontend/components/trading_desk/RunHistoryList.tsx` | 历史列表 + 回放入口 |
| `frontend/app/trading-desk/page.tsx` | 接入历史面板 |

---

## Task 1: stage_map —— 节点映射表

**Files:**
- Create: `app/services/trading_desk/engines/stage_map.py`
- Test: `tests/services/trading_desk/test_stage_map.py`

- [ ] **Step 1: 写失败测试**

```python
"""stage_map：LangGraph 节点名与事件协议 stage 的映射。"""

from __future__ import annotations

import pytest

from app.services.trading_desk.engines import stage_map


def test_agent_nodes_cover_all_semantic_nodes() -> None:
    """interrupt_before 要挂的 13 个语义节点，一个不能少。"""
    assert set(stage_map.AGENT_NODES) == {
        "Market Analyst", "Social Analyst", "News Analyst", "Fundamentals Analyst",
        "Situation Summariser", "Bull Researcher", "Bear Researcher",
        "Research Manager", "Trader",
        "Aggressive Analyst", "Conservative Analyst", "Neutral Analyst",
        "Risk Judge",
    }


def test_pipeline_nodes_are_excluded() -> None:
    """tools_* 与 Msg Clear * 是管道节点，不产生用户可见事件。"""
    assert not stage_map.is_agent_node("tools_market")
    assert not stage_map.is_agent_node("Msg Clear Market")
    assert stage_map.is_agent_node("Bull Researcher")


def test_stage_of_covers_every_agent_node() -> None:
    for node in stage_map.AGENT_NODES:
        assert stage_map.stage_of(node) is not None, f"{node} 缺 stage 映射"


def test_stage_of_returns_none_for_unknown() -> None:
    assert stage_map.stage_of("tools_market") is None
    assert stage_map.stage_of("whatever") is None


def test_debate_meta_for_researchers() -> None:
    bull = stage_map.debate_meta("Bull Researcher", round_no=2)
    assert bull is not None
    assert bull.polarity == "bull"
    assert bull.debate_id == "research"
    assert bull.round == 2

    aggr = stage_map.debate_meta("Aggressive Analyst", round_no=1)
    assert aggr is not None
    assert aggr.debate_id == "risk"
    assert aggr.polarity == "bull"          # 激进派偏多
    assert stage_map.debate_meta("Conservative Analyst", 1).polarity == "bear"
    assert stage_map.debate_meta("Neutral Analyst", 1).polarity == "neutral"


def test_debate_meta_none_for_non_debate_nodes() -> None:
    assert stage_map.debate_meta("Market Analyst", 1) is None


def test_display_defaults() -> None:
    d = stage_map.stage_of("Situation Summariser")
    assert d is not None
    assert d.id == "situation_summary"
    assert d.name == "情境摘要"
    assert d.group == "system"
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/services/trading_desk/test_stage_map.py -q
```

- [ ] **Step 3: 实现**

```python
"""LangGraph 节点名与事件协议 stage 的映射表。

翻译器只认这里的信息；tradingagents 改节点名时集中改这一处。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.trading_desk import Polarity, StageDescriptor, StageGroup


@dataclass(frozen=True)
class DebateMeta:
    debate_id: str
    side: str
    side_label: str
    polarity: Polarity


# 节点名 -> (stage_id, 中文名, role, group)
_NODE_TO_STAGE: dict[str, tuple[str, str, str, StageGroup]] = {
    "Market Analyst": ("market_analyst", "技术面分析师", "价格行为", "analyst"),
    "Social Analyst": ("social_analyst", "社交情绪", "舆情", "analyst"),
    "News Analyst": ("news_analyst", "消息与新闻", "资讯流", "analyst"),
    "Fundamentals Analyst": ("fundamentals_analyst", "基本面分析师", "价值", "analyst"),
    "Situation Summariser": ("situation_summary", "情境摘要", "汇总", "system"),
    "Bull Researcher": ("research_debate", "研究员辩论", "多空对辩", "debate"),
    "Bear Researcher": ("research_debate", "研究员辩论", "多空对辩", "debate"),
    "Research Manager": ("research_manager", "研究主管", "裁定", "manager"),
    "Trader": ("trader", "交易员", "综合", "trader"),
    "Aggressive Analyst": ("risk_debate", "风控委员会", "三方评议", "debate"),
    "Conservative Analyst": ("risk_debate", "风控委员会", "三方评议", "debate"),
    "Neutral Analyst": ("risk_debate", "风控委员会", "三方评议", "debate"),
    "Risk Judge": ("risk_judge", "风控裁决", "最终决策", "manager"),
}

# 辩论参与方的门派信息。风控三方：激进=偏多、保守=偏空、中立=中性
_DEBATE_META: dict[str, DebateMeta] = {
    "Bull Researcher": DebateMeta("research", "bull", "多头研究员", "bull"),
    "Bear Researcher": DebateMeta("research", "bear", "空头研究员", "bear"),
    "Aggressive Analyst": DebateMeta("risk", "aggressive", "激进派", "bull"),
    "Conservative Analyst": DebateMeta("risk", "conservative", "保守派", "bear"),
    "Neutral Analyst": DebateMeta("risk", "neutral", "中立派", "neutral"),
}

AGENT_NODES = tuple(_NODE_TO_STAGE)

# 发言人显示信息：节点名 -> (显示名, 头像缩写, role)
_NODE_DISPLAY: dict[str, tuple[str, str, str]] = {
    "Market Analyst": ("技术面分析师", "TA", "价格行为"),
    "Social Analyst": ("社交情绪", "SA", "舆情"),
    "News Analyst": ("消息与新闻", "NA", "资讯流"),
    "Fundamentals Analyst": ("基本面分析师", "FA", "价值"),
    "Situation Summariser": ("情境摘要", "SS", "汇总"),
    "Bull Researcher": ("多头研究员", "BR", "研究员"),
    "Bear Researcher": ("空头研究员", "BE", "研究员"),
    "Research Manager": ("研究主管", "RM", "裁定"),
    "Trader": ("交易员", "TR", "综合"),
    "Aggressive Analyst": ("激进派", "AG", "风控"),
    "Conservative Analyst": ("保守派", "CO", "风控"),
    "Neutral Analyst": ("中立派", "NE", "风控"),
    "Risk Judge": ("风控裁决", "RJ", "最终决策"),
}

# 历史发言前缀（tradingagents 在 debate_state 里加的），渲染前剥掉
_SPEAKER_PREFIXES = ("Bull Analyst: ", "Bear Analyst: ", "Aggressive Analyst: ",
                     "Conservative Analyst: ", "Neutral Analyst: ", "Judge: ")


def is_agent_node(node: str) -> bool:
    return node in _NODE_TO_STAGE


def stage_of(node: str) -> StageDescriptor | None:
    entry = _NODE_TO_STAGE.get(node)
    if entry is None:
        return None
    stage_id, name, role, group = entry
    return StageDescriptor(id=stage_id, name=name, role=role, group=group)


def display_of(node: str) -> tuple[str, str, str] | None:
    return _NODE_DISPLAY.get(node)


def debate_meta(node: str, round_no: int) -> DebateMeta | None:
    """辩论节点取门派信息；非辩论节点返回 None。

    round_no 只是签名占位（由调用方填进 DebateTurnData），映射表本身不存轮次。
    """
    return _DEBATE_META.get(node)
```

同时补上剥前缀函数：

```python
def strip_speaker_prefix(text: str) -> str:
    for prefix in _SPEAKER_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix):]
    return text
```

- [ ] **Step 4: 运行测试通过后提交**

```bash
uv run pytest tests/services/trading_desk/test_stage_map.py -v
git add app/services/trading_desk/engines/stage_map.py tests/services/trading_desk/test_stage_map.py
git commit -m "feat(trading-desk): 节点映射表"
```

---

## Task 2: 信号抽取

**Files:**
- Create: `app/services/trading_desk/signal_extract.py`
- Test: `tests/services/trading_desk/test_signal_extract.py`

- [ ] **Step 1: 写失败测试**

```python
"""信号抽取：从分析师报告文本抽 {dir, conf}。"""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.services.trading_desk import signal_extract


def test_prompt_asks_for_strict_json() -> None:
    prompt = signal_extract.build_prompt("基本面", "营收增长但估值偏高。")
    assert "bull" in prompt and "bear" in prompt and "neutral" in prompt
    assert "conf" in prompt


async def test_extract_parses_valid_json() -> None:
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(return_value='{"dir": "bull", "conf": 72}')

    result = await signal_extract.extract_signal(fake_llm, stage_name="基本面", report="……")  # type: ignore[arg-type]

    assert result == ("bull", 72)


async def test_extract_clamps_confidence() -> None:
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(return_value='{"dir": "bull", "conf": 130}')

    result = await signal_extract.extract_signal(fake_llm, stage_name="基本面", report="……")  # type: ignore[arg-type]

    assert result == ("bull", 100)


async def test_extract_degrades_to_neutral_on_garbage() -> None:
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(return_value="模型抽风了，这不是 JSON")

    result = await signal_extract.extract_signal(fake_llm, stage_name="基本面", report="……")  # type: ignore[arg-type]

    # 降级为中性低置信，绝不静默编方向（spec §4.6）
    assert result[0] == "neutral"
    assert result[1] < 50


async def test_extract_degrades_on_exception() -> None:
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(side_effect=RuntimeError("超时"))

    result = await signal_extract.extract_signal(fake_llm, stage_name="基本面", report="……")  # type: ignore[arg-type]

    assert result[0] == "neutral"
```

- [ ] **Step 2: 确认失败后实现**

```python
"""从分析师报告文本抽取 {dir, conf} 信号。

TradingAgents 的分析师只产出大段文字 report，不产出结构化信号；
共识条与流程条上的信号 chip 全靠本模块补齐（spec §4.6）。

约束：
  - 用 quick 档模型（llm_registry 的 TRADING_DESK_QUICK_MODEL 回落默认）
  - 抽取失败降级 neutral 低置信，绝不静默编方向
  - 每份 report 一次调用，约 +4 次/run，计入成本预期
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from app.core.logging import logger

_DEGRADE = ("neutral", 20)


class InvokableLLM(Protocol):
    async def ainvoke(self, prompt: str) -> str: ...


def build_prompt(stage_name: str, report: str) -> str:
    return (
        f"你是投研分析助手。下面是「{stage_name}」对某标的的一段分析报告。\n"
        "请只输出一个 JSON 对象（不要任何其他文字），形如：\n"
        '{"dir": "bull|bear|neutral", "conf": 0-100 的整数}\n'
        "dir 表示该报告整体立场（看多/看空/中性），conf 表示立场的明确程度（越笃定越高，"
        "骑墙观点给低分）。\n\n报告内容：\n" + report[:4000]
    )


def _parse_reply(reply: str) -> tuple[str, int] | None:
    """从回复中挖出 JSON。容忍 markdown 代码块包裹。"""
    match = re.search(r"\{[^{}]*\}", reply, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

    direction = str(data.get("dir", "")).lower()
    if direction not in ("bull", "bear", "neutral"):
        return None
    try:
        conf = int(data.get("conf", 0))
    except (TypeError, ValueError):
        return None
    return direction, max(0, min(100, conf))


async def extract_signal(llm: InvokableLLM, *, stage_name: str, report: str) -> tuple[str, int]:
    """抽取信号；任何失败都降级为中性低置信。"""
    if not report.strip():
        return _DEGRADE
    try:
        reply = str(await llm.ainvoke(build_prompt(stage_name, report)))
    except Exception:
        logger.exception("signal_extract_failed", stage=stage_name)
        return _DEGRADE

    parsed = _parse_reply(reply)
    if parsed is None:
        logger.warning("signal_extract_unparseable", stage=stage_name, reply=reply[:200])
        return _DEGRADE
    return parsed


def quick_llm():
    """取 quick 档模型。延迟导入避免循环依赖。"""
    from app.services.llm.registry import llm_registry
    from app.core.config import settings

    llm, _ = llm_registry.get_or_default(settings.TRADING_DESK_QUICK_MODEL or None)
    return llm
```

- [ ] **Step 3: 测试通过后提交**

```bash
uv run pytest tests/services/trading_desk/test_signal_extract.py -v
git add app/services/trading_desk/signal_extract.py tests/services/trading_desk/test_signal_extract.py
git commit -m "feat(trading-desk): 信号抽取"
```

---

## Task 3: 流翻译器（纯函数）

把 LangGraph 双模式 chunk 翻译成事件。先写纯函数 + fixtures 测试，引擎只做 IO。

**Files:**
- Create: `app/services/trading_desk/engines/stream_translator.py`
- Test: `tests/services/trading_desk/test_stream_translator.py`

- [ ] **Step 1: 写失败测试**

```python
"""流翻译器：LangGraph chunk -> 事件协议。纯函数测试，不跑图。"""

from __future__ import annotations

from langchain_core.messages import AIMessageChunk, ToolMessage

from app.schemas.trading_desk import EventType
from app.services.trading_desk.engines import stream_translator as st


def _token_chunk(node: str, text: str) -> tuple[str, tuple]:
    msg = AIMessageChunk(content=text)
    return ("messages", (msg, {"langgraph_node": node}))


def _tool_chunk(node: str, tool: str) -> tuple[str, tuple]:
    msg = AIMessageChunk(content="", tool_call_chunks=[{"name": tool, "args": '{"ticker": "NVDA"}', "id": "t1", "index": 0, "type": "tool_call_chunk"}])
    return ("messages", (msg, {"langgraph_node": node}))


def test_token_from_agent_node_becomes_agent_token() -> None:
    tr = st.StreamTranslator(run_id="r1")
    events = tr.feed(_token_chunk("Market Analyst", "回调后"))

    assert [e.type for e in events] == []
    # 第一片 token 先开 turn
    tr.feed(_token_chunk("Market Analyst", "站稳"))
    state = tr.snapshot()
    turn_id = state["current_turn"]["Market Analyst"]
    assert turn_id
    assert tr.text_of(turn_id) == "回调后站稳"


def test_tool_message_is_ignored() -> None:
    tr = st.StreamTranslator(run_id="r1")
    msg = ToolMessage(content="工具结果", tool_call_id="t1")
    events = tr.feed(("messages", (msg, {"langgraph_node": "tools_market"})))

    assert events == []


def test_tool_call_chunk_becomes_agent_tool_call() -> None:
    tr = st.StreamTranslator(run_id="r1")
    tr.feed(_token_chunk("Market Analyst", ""))
    events = tr.feed(_tool_chunk("Market Analyst", "get_stock_data"))

    assert [e.type for e in events] == [EventType.AGENT_TOOL_CALL]
    assert events[0].data["tool"] == "get_stock_data"


def test_node_update_opens_and_closes_stages() -> None:
    tr = st.StreamTranslator(run_id="r1")
    tr.feed(_token_chunk("Market Analyst", "文本"))
    events = tr.feed(("updates", {"Market Analyst": {"messages": None, "market_report": "报告"}}))

    types = [e.type for e in events]
    assert EventType.STAGE_ACTIVE in types   # 第一次见到该 stage
    assert EventType.TURN_DONE in types
    assert EventType.STAGE_DONE in types


def test_report_completion_marks_extractable_signal() -> None:
    tr = st.StreamTranslator(run_id="r1")
    tr.feed(_token_chunk("News Analyst", "消息面"))
    tr.feed(("updates", {"News Analyst": {"news_report": "报告"}}))

    assert tr.pending_reports() == [("news_analyst", "消息与新闻", "报告")]


def test_debate_turn_events_carry_round() -> None:
    tr = st.StreamTranslator(run_id="r1")
    tr.feed(_token_chunk("Bull Researcher", "论点"))
    events = tr.feed(("updates", {"Bull Researcher": {"investment_debate_state": object()}}))

    debate = [e for e in events if e.type is EventType.DEBATE_TURN]
    assert debate[0].data["polarity"] == "bull"
    assert debate[0].data["round"] == 1
    # 第二轮再执行时轮次递增
    tr.feed(_token_chunk("Bull Researcher", "第二轮"))
    events = tr.feed(("updates", {"Bull Researcher": {"investment_debate_state": object()}}))
    debate = [e for e in events if e.type is EventType.DEBATE_TURN]
    assert debate[0].data["round"] == 2


def test_final_trade_decision_flags_verdict_ready() -> None:
    tr = st.StreamTranslator(run_id="r1")
    tr.feed(("updates", {"Risk Judge": {"final_trade_decision": "BUY 一切"}}))

    assert tr.verdict_text() == "BUY 一切"


def test_clears_current_turn_text_between_executions() -> None:
    """同一节点第二次执行（如辩论第二轮）不叠加上一轮文本。"""
    tr = st.StreamTranslator(run_id="r1")
    tr.feed(_token_chunk("Bear Researcher", "第一轮"))
    tr.feed(("updates", {"Bear Researcher": {"investment_debate_state": object()}}))
    tr.feed(_token_chunk("Bear Researcher", "第二轮"))
    tr.feed(("updates", {"Bear Researcher": {"investment_debate_state": object()}}))

    rounds = [e.data["round"] for e in tr.events if e.type is EventType.DEBATE_TURN]
    assert rounds == [1, 2]
```

- [ ] **Step 2: 实现翻译器**

```python
"""LangGraph 双模式 chunk -> 事件协议 的纯翻译器。

设计：StreamTranslator 是一个有状态的折叠器——引擎把 astream 的
chunk 原样喂进来，feed() 返回需要外发的事件列表。这样翻译逻辑可以
完全脱开 LangGraph 与 Redis 做单元测试。

不在这里做：signal_extract（引擎在 pending_reports 出现时另行调用）、
verdict 解析（引擎在 verdict_text 出现时另行调用）。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessageChunk

from app.schemas.trading_desk import (
    DebateTurnData,
    EventType,
    StageData,
    ToolCallData,
    TokenData,
    TradingDeskEvent,
    TurnDoneData,
    TurnStartedData,
)
from app.services.trading_desk.engines import stage_map


class StreamTranslator:
    """把 (mode, payload) chunk 折叠成事件。"""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.events: list[TradingDeskEvent] = []
        self._current_turn: dict[str, str] = {}     # node -> turn_id
        self._turn_text: dict[str, list[str]] = {}  # turn_id -> token 片段
        self._stage_states: set[str] = set()        # 已 active 的 stage_id
        self._node_runs: dict[str, int] = {}        # node -> 执行次数
        self._reports: list[tuple[str, str, str]] = []  # (stage_id, name, report)
        self._verdict: str | None = None
        self._seq = 0

    # ── 对外接口 ─────────────────────────────────────────

    def feed(self, chunk: Any) -> list[TradingDeskEvent]:
        """喂入一个 astream chunk，返回产生的事件（已记录在 self.events）。"""
        produced: list[TradingDeskEvent] = []
        if not isinstance(chunk, tuple) or len(chunk) != 2:
            return produced
        mode, payload = chunk
        if mode == "messages":
            produced = self._feed_message(payload)
        elif mode == "updates":
            produced = self._feed_updates(payload)
        self.events.extend(produced)
        return produced

    def snapshot(self) -> dict[str, str]:
        return dict(self._current_turn)

    def text_of(self, turn_id: str) -> str:
        return "".join(self._turn_text.get(turn_id, []))

    def pending_reports(self) -> list[tuple[str, str, str]]:
        out, self._reports = self._reports, []
        return out

    def verdict_text(self) -> str | None:
        text, self._verdict = self._verdict, None
        return text

    # ── messages 模式 ────────────────────────────────────

    def _feed_message(self, payload: Any) -> list[TradingDeskEvent]:
        if not isinstance(payload, tuple) or len(payload) != 2:
            return []
        message, metadata = payload
        node = str(metadata.get("langgraph_node") or "") if isinstance(metadata, dict) else ""
        if not stage_map.is_agent_node(node):
            return []  # tools_* / Msg Clear * 的消息不进推理流

        if isinstance(message, AIMessageChunk):
            turn_id = self._ensure_turn(node)
            produced: list[TradingDeskEvent] = []
            for tc in message.tool_call_chunks or []:
                if tc.get("name"):
                    produced.append(self._emit(EventType.AGENT_TOOL_CALL, ToolCallData(
                        turn_id=turn_id, tool=str(tc["name"]),
                    )))
            content = message.content
            if isinstance(content, str) and content:
                self._turn_text[turn_id].append(content)
                produced.append(self._emit(EventType.AGENT_TOKEN, TokenData(turn_id=turn_id, text=content)))
            return produced
        return []

    # ── updates 模式 ─────────────────────────────────────

    def _feed_updates(self, payload: Any) -> list[TradingDeskEvent]:
        if not isinstance(payload, dict):
            return []
        produced: list[TradingDeskEvent] = []

        for node, update in payload.items():
            if not stage_map.is_agent_node(node) or not isinstance(update, dict):
                continue
            self._node_runs[node] = self._node_runs.get(node, 0) + 1
            turn_id = self._current_turn.get(node)

            # stage 生命周期：第一次见到该节点时开 stage
            stage = stage_map.stage_of(node)
            if stage is not None and stage.id not in self._stage_states:
                self._stage_states.add(stage.id)
                produced.append(self._emit(EventType.STAGE_ACTIVE, StageData(stage_id=stage.id)))

            if turn_id:
                produced.append(self._emit(EventType.TURN_DONE, TurnDoneData(turn_id=turn_id)))
                self._current_turn.pop(node, None)

            meta = stage_map.debate_meta(node, self._node_runs[node])
            if meta is not None and turn_id:
                display = stage_map.display_of(node)
                produced.append(self._emit(EventType.DEBATE_TURN, DebateTurnData(
                    stage_id=stage.id if stage else "",
                    debate_id=meta.debate_id,
                    side=meta.side,
                    side_label=meta.side_label,
                    polarity=meta.polarity,
                    round=self._node_runs[node],
                    turn_id=turn_id,
                )))

            # report 完成检测（signal_extract 的触发点）
            for key, stage_name in (
                ("market_report", "技术面分析师"),
                ("sentiment_report", "社交情绪"),
                ("news_report", "消息与新闻"),
                ("fundamentals_report", "基本面分析师"),
            ):
                if key in update and update[key]:
                    self._reports.append((stage.id if stage else key, stage_name, str(update[key])))

            if "final_trade_decision" in update and update["final_trade_decision"]:
                self._verdict = str(update["final_trade_decision"])

            produced.append(self._emit(EventType.STAGE_DONE, StageData(stage_id=stage.id if stage else "")))

        return produced

    # ── 内部 ─────────────────────────────────────────────

    def _ensure_turn(self, node: str) -> str:
        if node not in self._current_turn:
            display = stage_map.display_of(node)
            turn_id = f"{node}-{self._node_runs.get(node, 0) + 1}"
            self._current_turn[node] = turn_id
            self._turn_text[turn_id] = []
            self._emit_to_history(TurnStartedData(
                turn_id=turn_id,
                stage_id=stage_map.stage_of(node).id if stage_map.stage_of(node) else "",
                name=display[0] if display else node,
                role=display[2] if display else "",
                avatar=display[1] if display else "",
            ))
        return self._current_turn[node]

    def _emit(self, type_: EventType, payload: Any) -> TradingDeskEvent:
        return TradingDeskEvent.of(self.run_id, type_, payload)

    def _emit_to_history(self, payload: Any) -> None:
        self.events.append(TradingDeskEvent.of(self.run_id, EventType.TURN_STARTED, payload))
```

- [ ] **Step 3: 跑测试，修到绿**

```bash
uv run pytest tests/services/trading_desk/test_stream_translator.py -v
```

测试与实现可能有出入（如 TURN_STARTED 在第一片 token 时才发），以测试语义为准修实现——测试即契约。

- [ ] **Step 4: 提交**

```bash
git add app/services/trading_desk/engines/stream_translator.py tests/services/trading_desk/test_stream_translator.py
git commit -m "feat(trading-desk): 流翻译器"
```

---

## Task 4: TradingAgentsEngine —— 图构建与纯流式路径

先做不带 HITL 的完整路径（checkpointer 挂上但不 interrupt），HITL 循环放 Task 5。

**Files:**
- Create: `app/services/trading_desk/engines/tradingagents.py`
- Test: `tests/services/trading_desk/test_ta_engine.py`

- [ ] **Step 1: 写测试（假 LLM 全图跑，验证事件序列）**

```python
"""TradingAgentsEngine 集成测试：假 LLM 跑全图，验证事件协议映射。"""

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

from app.schemas.trading_desk import EventType
from app.services.trading_desk.engine_base import ControlHandle, RunContext
from app.services.trading_desk.engines.tradingagents import TradingAgentsEngine

HUMAN_NOTE = "【人工意见】把风险权重调高。"


class FakeLLM(BaseChatModel):
    """轮流返回不同长度文本的假模型；第 1 次带 tool_call 走一遍工具循环。"""

    calls: int = Field(default=0)
    prompts: list[str] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls += 1
        self.prompts.append("\n".join(str(m.content) for m in messages))
        if self.calls == 1:
            msg = AIMessage(content="", tool_calls=[
                {"name": "get_stock_data", "args": {"ticker": "NVDA"}, "id": "c1"}
            ])
        else:
            msg = AIMessage(content=(
                "FINAL TRANSACTION PROPOSAL: **BUY**\n"
                "```json\n{\"signal\": \"BUY\", \"confidence\": 0.7, \"size_fraction\": 0.05,"
                " \"target_price\": 200, \"stop_loss\": 160, \"time_horizon_days\": 30,"
                " \"rationale\": \"测试理由\"}\n```"
            ))
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def bind_tools(self, tools, **kwargs):
        return self


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


def _ctx(**kwargs) -> RunContext:
    async def false() -> bool:
        return False

    async def no_notes() -> list[str]:
        return []

    defaults = dict(
        run_id="r1", ticker="NVDA", trade_date="2026-08-30",
        control=ControlHandle(is_paused=false, is_cancelled=false, drain_notes=no_notes),
    )
    defaults.update(kwargs)
    return RunContext(**defaults)


def test_describe_reports_full_topology() -> None:
    d = TradingAgentsEngine().describe()

    assert d.engine.startswith("tradingagents")
    assert d.capabilities.supports_pause is True
    assert d.capabilities.supports_inject is True
    ids = [s.id for s in d.stages]
    assert ids[0] == "market_analyst" and ids[-1] == "risk_judge"
    assert len(ids) == 10  # 4 分析师 + 摘要 + 辩论 + 主管 + 交易员 + 风控辩论 + 裁决


@pytest.mark.asyncio
async def test_full_run_emits_protocol_events(tmp_path: Path, fake_llm: FakeLLM) -> None:
    engine = TradingAgentsEngine(checkpointer=InMemorySaver(), results_dir=tmp_path, llm_override=fake_llm)
    events = [e async for e in engine.astream(_ctx())]

    types = [e.type for e in events]
    assert EventType.AGENT_TOKEN in types
    assert EventType.AGENT_TOOL_CALL in types
    assert EventType.DEBATE_TURN in types
    assert EventType.VERDICT in types
    assert types[-1] is EventType.VERDICT

    verdict = next(e for e in events if e.type is EventType.VERDICT)
    assert verdict.data["signal"] == "BUY"
    assert verdict.data["confidence"] == pytest.approx(0.7)

    # 每个 stage 恰好 active/done 一次
    actives = [e.data["stage_id"] for e in events if e.type is EventType.STAGE_ACTIVE]
    dones = [e.data["stage_id"] for e in events if e.type is EventType.STAGE_DONE]
    assert actives == dones and len(actives) == 10


@pytest.mark.asyncio
async def test_signals_extracted_from_reports(tmp_path: Path, fake_llm: FakeLLM) -> None:
    class SignalStub:
        async def ainvoke(self, prompt: str) -> str:
            return '{"dir": "bull", "conf": 80}'

    engine = TradingAgentsEngine(
        checkpointer=InMemorySaver(), results_dir=tmp_path, llm_override=fake_llm,
        extractor_llm=SignalStub(),
    )
    events = [e async for e in engine.astream(_ctx())]

    signals = [e for e in events if e.type is EventType.AGENT_SIGNAL]
    assert len(signals) == 4  # 四份 report
    assert all(s.data["extracted"] is True for s in signals)
    assert all(s.data["dir"] == "bull" for s in signals)
    consensus = [e for e in events if e.type is EventType.CONSENSUS_UPDATE]
    assert consensus[-1].data == {"bull": 4, "neutral": 0, "bear": 0, "lean": "明显偏多"}
```

- [ ] **Step 2: 实现引擎**

```python
"""TradingAgentsEngine —— 包装 tradingagents 0.7.0。

关键机制（均已在计划一探针验证）：
  - graph.builder.compile(checkpointer, interrupt_before=AGENT_NODES) 重编译
  - ta.__dict__ 预置抢占 cached_property，注入平台 llm_registry 实例
  - astream(stream_mode=["messages","updates"]) 双模式取流
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from app.core.config import settings
from app.core.logging import logger
from app.schemas.trading_desk import (
    ConsensusData,
    EngineCapabilities,
    EngineDescriptor,
    EventType,
    HumanNoteData,
    Polarity,
    SignalData,
    VerdictData,
    TradingDeskEvent,
)
from app.services.trading_desk.engine_base import RunContext
from app.services.trading_desk.engines import stage_map
from app.services.trading_desk.engines.stream_translator import StreamTranslator
from app.services.trading_desk.signal_extract import extract_signal, quick_llm

# 注入目标（spec §5.3）：交易员前后的人工意见分别追加到这两个字段
_PRE_TRADER_FIELD = "news_report"
_POST_TRADER_FIELD = "trader_investment_plan"


class TradingAgentsEngine:
    """tradingagents 引擎。生产路径用平台 LLM；测试注入 llm_override。"""

    name = "tradingagents"

    def __init__(
        self,
        *,
        checkpointer: object | None = None,
        results_dir: Path | None = None,
        llm_override: object | None = None,
        extractor_llm: object | None = None,
    ) -> None:
        self._checkpointer = checkpointer
        self._results_dir = results_dir
        self._llm_override = llm_override
        self._extractor_llm = extractor_llm

    def describe(self) -> EngineDescriptor:
        import tradingagents
        import importlib.metadata as md

        stages = []
        seen: set[str] = set()
        for node in stage_map.AGENT_NODES:
            d = stage_map.stage_of(node)
            if d and d.id not in seen:
                seen.add(d.id)
                stages.append(d)
        return EngineDescriptor(
            engine=f"tradingagents/{md.version('tradingagents')}",
            capabilities=EngineCapabilities(supports_pause=True, supports_inject=True),
            stages=stages,
        )

    async def astream(self, ctx: RunContext) -> AsyncIterator[TradingDeskEvent]:
        from tradingagents import TradingAgentsConfig, TradingAgentsGraph

        config = TradingAgentsConfig(
            results_dir=self._results_dir or Path(tempfile.gettempdir()) / "trading_desk",
            llm_provider="openai",  # 注入生效后仅是日志元数据
            deep_think_llm=settings.TRADING_DESK_DEEP_MODEL or "platform-default",
            quick_think_llm=settings.TRADING_DESK_QUICK_MODEL or "platform-default",
            response_language="zh-CN",
            max_debate_rounds=settings.TRADING_DESK_MAX_DEBATE_ROUNDS,
            max_risk_discuss_rounds=settings.TRADING_DESK_MAX_RISK_ROUNDS,
            max_recur_limit=100,
        )
        ta = TradingAgentsGraph(config=config)

        if self._llm_override is not None:
            ta.__dict__["deep_thinking_llm"] = self._llm_override
            ta.__dict__["quick_thinking_llm"] = self._llm_override
        else:
            deep, _ = llm_registry().get_or_default(settings.TRADING_DESK_DEEP_MODEL or None)
            quick, _ = llm_registry().get_or_default(settings.TRADING_DESK_QUICK_MODEL or None)
            ta.__dict__["deep_thinking_llm"] = deep
            ta.__dict__["quick_thinking_llm"] = quick

        checkpointer = self._checkpointer or await _default_checkpointer()
        compiled = ta.graph.builder.compile(
            checkpointer=checkpointer,
            interrupt_before=list(stage_map.AGENT_NODES),
        )

        cfg = {"configurable": {"thread_id": ctx.run_id}, "recursion_limit": 100}
        init = ta.propagator.create_initial_state(ctx.ticker, ctx.trade_date)

        translator = StreamTranslator(run_id=ctx.run_id)
        extractor = self._extractor_llm or quick_llm()
        signals: list[tuple[Polarity, int]] = []

        async def pump(chunks: AsyncIterator) -> bool:
            """消费一批图输出 chunk：翻译、抽信号、发 verdict。False = 已取消。"""
            async for chunk in chunks:
                if await ctx.control.is_cancelled():
                    return False
                for event in translator.feed(chunk):
                    yield event  # type: ignore[misc]  —— 见下：pump 实为异步生成器
                async for event in self._signal_events(translator, extractor, signals):
                    yield event
                verdict = translator.verdict_text()
                if verdict:
                    yield self._build_verdict(ta, verdict)
            return True

        # 主循环：跑图到下一个 interrupt → 暂停等待 → 注入意见 → 恢复
        while True:
            async for event in pump(compiled.astream(init, cfg, stream_mode=["messages", "updates"])):
                yield event
            if await ctx.control.is_cancelled():
                return

            state = await compiled.aget_state(cfg)
            if not state.next:  # 图跑完了
                return

            await self._wait_if_paused(ctx)
            if await ctx.control.is_cancelled():
                return
            async for event in self._inject_notes(compiled, cfg, state):
                yield event
            init = None  # 恢复执行用 None

    # ── 辅助 ─────────────────────────────────────────────

    async def _signal_events(self, translator, extractor, signals) -> AsyncIterator[TradingDeskEvent]:
        """pending_reports → agent.signal + consensus.update。"""
        from app.schemas.trading_desk import SignalData

        for stage_id, stage_name, report in translator.pending_reports():
            direction, conf = await extract_signal(extractor, stage_name=stage_name, report=report)
            signals.append((direction, conf))  # type: ignore[arg-type]
            yield TradingDeskEvent.of(self_run_id, EventType.AGENT_SIGNAL, SignalData(
                stage_id=stage_id, name=stage_name, dir=direction, conf=conf, extracted=True,
            ))
            yield TradingDeskEvent.of(self_run_id, EventType.CONSENSUS_UPDATE, _consensus(signals))

    def _build_verdict(self, ta, text: str) -> TradingDeskEvent:
        rec = ta.process_signal(text)
        return TradingDeskEvent.of(self_run_id, EventType.VERDICT, VerdictData(
            signal=rec.signal, confidence=rec.confidence, size_fraction=rec.size_fraction,
            entry_reference_price=rec.entry_reference_price, target_price=rec.target_price,
            stop_loss=rec.stop_loss, currency=rec.currency,
            time_horizon_days=rec.time_horizon_days, rationale=rec.rationale,
            warning_message=rec.warning_message,
        ))

    async def _wait_if_paused(self, ctx: RunContext) -> None:
        while await ctx.control.is_paused():
            if await ctx.control.is_cancelled():
                return
            await asyncio.sleep(0.5)

    async def _inject_notes(self, compiled, cfg, state, ctx) -> AsyncIterator[TradingDeskEvent]:
        """把积压意见嫁接进引擎状态（计划一探针验证的路径）。"""
        order = list(stage_map.AGENT_NODES)
        trader_idx = order.index("Trader")

        for note in await ctx.control.drain_notes():
            next_idx = order.index(state.next[0]) if state.next[0] in order else trader_idx
            field = _PRE_TRADER_FIELD if next_idx <= trader_idx else _POST_TRADER_FIELD

            values = state.values if isinstance(state.values, dict) else vars(state.values)
            current = str(values.get(field, "") or "")
            await compiled.aupdate_state(cfg, {field: f"{current}\n\n---\n【人工补充意见】{note}"})

            yield TradingDeskEvent.of(ctx.run_id, EventType.HUMAN_NOTE, HumanNoteData(
                text=note, injected_into=field,
            ))
            state = await compiled.aget_state(cfg)  # aupdate 后重新取，连续注入不丢
```

**实现注意（写给执行者）：**

1. `pump` 声明为 `async def ... yield` 的嵌套异步生成器（不需要返回值——把取消判断改为在循环内 `return` 即可，上面骨架里 `return False` 的写法改为直接 return）。`self_run_id` 即 `ctx.run_id`，实现时直接用 `ctx.run_id`，骨架里的 `self_run_id` 是示意。
2. `_consensus` 从 `engines/mock.py` 里把同名函数提为共享工具（挪到 `app/services/trading_desk/consensus.py` 或直接 import mock 的实现——选前者，mock 改为 import 它）。
3. `tempfile` 需要 `import tempfile`；`llm_registry` 即 `from app.services.llm.registry import llm_registry`（模块级单例）。
4. `_default_checkpointer`：复用 `app/core/langgraph/graph.py` 的 AsyncPostgresSaver 连接池逻辑（查看 `_get_connection_pool`）；pool 不可用（本地无 DB）时回退 `InMemorySaver()` 并打 warning。抽成模块级函数并单测「无 DB 时回退 InMemory」。
5. `_inject_notes` 完整逻辑：`notes = await ctx.control.drain_notes()`；对每条 note，按 `list(stage_map.AGENT_NODES).index("Trader") < list(stage_map.AGENT_NODES).index(state.next[0])` 判断目标字段（之前 → `news_report`，之后 → `trader_investment_plan`）；从 `state.values`（dict 或 AgentState 都可能）读当前值，`await compiled.aupdate_state(cfg, {field: f"{current}\n\n---\n【人工补充意见】{note}"})`，并 `yield HUMAN_NOTE(text=note, injected_into=field)`。注入前 `state` 要重新 `aget_state`（aupdate 后值会变）。

- [ ] **Step 3: 跑测试修到绿，提交**

```bash
uv run pytest tests/services/trading_desk/test_ta_engine.py -v
git add app/services/trading_desk/engines/tradingagents.py tests/services/trading_desk/test_ta_engine.py
git commit -m "feat(trading-desk): TradingAgentsEngine 流式路径"
```

---

## Task 5: HITL —— 暂停与注入（真实图验证）

Task 4 的骨架已含 HITL 循环；本任务补行为测试钉死它。

**Files:**
- Test: `tests/services/trading_desk/test_ta_engine_hitl.py`

- [ ] **Step 1: 写测试**

```python
"""TradingAgentsEngine 的 HITL 行为：暂停停在节点边界、注入进 prompt、取消早停。"""

from __future__ import annotations

from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.schemas.trading_desk import EventType
from app.services.trading_desk.engine_base import ControlHandle, RunContext
from app.services.trading_desk.engines.tradingagents import TradingAgentsEngine
from tests.services.trading_desk.test_ta_engine import FakeLLM, _ctx


@pytest.mark.asyncio
async def test_injected_note_reaches_downstream_prompt(tmp_path: Path) -> None:
    """注入的意见必须出现在下游 agent 的 prompt 里（spec §5.3 核心承诺）。"""
    fake = FakeLLM()
    notes = ["【人工意见】把出口管制风险的权重调高。"]
    ctx = _ctx(control=ControlHandle(
        is_paused=_always(False),
        is_cancelled=_always(False),
        drain_notes=_drain_once(notes),
    ))
    engine = TradingAgentsEngine(checkpointer=InMemorySaver(), results_dir=tmp_path, llm_override=fake)

    events = [e async for e in engine.astream(ctx)]

    # 事件面：human.note 出现且带 injected_into
    notes_ev = [e for e in events if e.type is EventType.HUMAN_NOTE]
    assert len(notes_ev) == 1
    assert notes_ev[0].data["injected_into"] == "news_report"
    # 数据面：注入文本进入了后续某次 LLM 调用的 prompt
    joined = "\n".join(fake.prompts)
    assert "把出口管制风险的权重调高" in joined


@pytest.mark.asyncio
async def test_pause_holds_at_boundary_and_resume_completes(tmp_path: Path) -> None:
    paused = {"flag": True}
    engine = TradingAgentsEngine(checkpointer=InMemorySaver(), results_dir=tmp_path, llm_override=FakeLLM())
    ctx = _ctx(control=ControlHandle(
        is_paused=lambda: _ret(paused["flag"]),
        is_cancelled=_always(False),
        drain_notes=_always([]),
    ))

    import asyncio
    collected: list = []

    async def collect() -> None:
        async for e in engine.astream(ctx):
            collected.append(e)

    task = asyncio.ensure_future(collect())
    await asyncio.sleep(0.5)          # 跑到第一个 interrupt 点并停住

    frozen = len(collected)
    await asyncio.sleep(0.3)          # 暂停期间不应有新事件
    assert len(collected) == frozen, "暂停期间仍在产出事件——没停在节点边界"

    paused["flag"] = False            # 恢复
    await asyncio.wait_for(task, timeout=30)

    types = [e.type for e in collected]
    assert EventType.VERDICT in types  # 恢复后跑完


def _always(v: bool):
    async def f() -> bool:
        return v
    return f


def _ret(v: bool):
    async def f() -> bool:
        return v
    return f


def _drain_once(notes: list[str]):
    async def f() -> list[str]:
        out = list(notes)
        notes.clear()
        return out
    return f
```

注：`test_pause_holds_at_boundary_and_resume_completes` 里通过事件流验证恢复即可；如需验证「暂停期间无新事件」，用共享 list 由引擎协程增量 append（实现时把 `_collect` 改为向传入 list append 的形式）。

- [ ] **Step 2: 跑测试修到绿（若 Task 4 骨架的 HITL 有 bug 在此修）**

```bash
uv run pytest tests/services/trading_desk/test_ta_engine_hitl.py -v
git add tests/services/trading_desk/test_ta_engine_hitl.py
git commit -m "test(trading-desk): 引擎 HITL 行为验证"
```

---

## Task 6: 引擎接线

**Files:**
- Modify: `app/api/v1/trading_desk.py`（get_engine）

- [ ] **Step 1: 改 get_engine**

```python
def get_engine() -> TradingEngine:
    """按配置选择引擎。tradingagents 走真实引擎；mock 回放固定剧本。"""
    if settings.TRADING_DESK_ENGINE == "tradingagents":
        from app.services.trading_desk.engines.tradingagents import TradingAgentsEngine

        return TradingAgentsEngine()
    return MockEngine()
```

- [ ] **Step 2: 更新 API 测试夹具**（`tests/api/test_trading_desk_api.py` 依赖 override，不受影响；确认既有测试仍绿）

```bash
uv run pytest tests/api/test_trading_desk_api.py tests/services/trading_desk/ -q
git add app/api/v1/trading_desk.py && git commit -m "feat(trading-desk): 接入 TradingAgentsEngine"
```

---

## Task 7: 落库模型与迁移

**Files:**
- Create: `app/models/trading_desk_run.py`
- 迁移: `alembic/versions/`（autogenerate）

- [ ] **Step 1: 模型**

```python
"""交易台运行记录。

Redis Stream 存逐 token 事件（TTL 7 天，服务实时与断线重连）；
本表存结构化摘要（turn 级全文），服务历史列表与回放。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlmodel import Column, Field, JSON

from app.db.base import UUIDModel


class TradingDeskRun(UUIDModel, table=True):
    __tablename__ = "trading_desk_run"

    user_id: int = Field(..., index=True, nullable=False)
    ticker: str = Field(..., index=True, nullable=False)
    trade_date: str = Field(...)
    engine: str = Field(default="")
    status: str = Field(default="running", index=True)
    # 结构化裁决（VerdictData dump）
    verdict: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    # [{name, dir, conf, extracted}]
    signals: list[dict[str, Any]] | None = Field(default=None, sa_column=Column(JSON))
    # [{turnId, name, role, avatar, text, human, debate, signal}]
    turns: list[dict[str, Any]] | None = Field(default=None, sa_column=Column(JSON))
    duration_ms: int = Field(default=0)
    finished_at: datetime | None = Field(default=None)
```

注意 `finished_at` 用 `datetime | None`，插入时 `datetime.now(UTC)`。

- [ ] **Step 2: 注册到 alembic 元数据**

查 `alembic/env.py` 如何 import 模型（通常有集中的 `app.models` 导入点或 `alembic/env.py` 里 import *）；把 `app.models.trading_desk_run` 加进去。

- [ ] **Step 3: 生成并应用迁移**

```bash
make migration MSG="add trading_desk_run"
# 检查生成的迁移文件只含 trading_desk_run 一张表；有多余改动则修 env 的 import 后重新生成
make migrate 2>/dev/null || uv run alembic upgrade head
```

- [ ] **Step 4: 提交**

```bash
git add app/models/trading_desk_run.py alembic/versions/
git commit -m "feat(trading-desk): 运行落库模型与迁移"
```

---

## Task 8: persistence 与历史端点

**Files:**
- Create: `app/services/trading_desk/persistence.py`
- Modify: `app/services/trading_desk/runner.py`（收尾落库）
- Modify: `app/api/v1/trading_desk.py`（GET /runs、GET /runs/{id}）
- Modify: `app/schemas/trading_desk.py`（响应 schema）
- Test: `tests/services/trading_desk/test_persistence.py`

- [ ] **Step 1: 写失败测试**

```python
"""persistence：从 Redis Stream 折叠事件为落库摘要。"""

from __future__ import annotations

from app.schemas.trading_desk import EventType, TokenData, TradingDeskEvent
from app.services.trading_desk.persistence import summarise


def _ev(t: EventType, **data) -> TradingDeskEvent:
    return TradingDeskEvent(type=t, run_id="r1", data=data)


EVENTS = [
    _ev(EventType.TURN_STARTED, turn_id="t1", stage_id="market", name="技术面", role="", avatar="TA"),
    _ev(EventType.AGENT_TOKEN, turn_id="t1", text="回调"),
    _ev(EventType.AGENT_TOKEN, turn_id="t1", text="站稳"),
    _ev(EventType.TURN_DONE, turn_id="t1"),
    _ev(EventType.AGENT_SIGNAL, stage_id="market", name="技术面", dir="bull", conf=64, turn_id="t1", extracted=True),
    _ev(EventType.HUMAN_NOTE, text="把风险权重调高", injected_into="news_report"),
    _ev(EventType.VERDICT, signal="BUY", confidence=0.66, size_fraction=0.04, rationale="r"),
    _ev(EventType.RUN_FINISHED, status="completed", duration_ms=1234),
]


def test_summarise_folds_tokens_into_turn_text() -> None:
    s = summarise(EVENTS)
    assert s["turns"][0]["text"] == "回调站稳"
    assert s["turns"][0]["name"] == "技术面"


def test_summarise_keeps_human_turn() -> None:
    s = summarise(EVENTS)
    human = [t for t in s["turns"] if t["human"]]
    assert human[0]["text"] == "把风险权重调高"


def test_summarise_extracts_verdict_signals_status() -> None:
    s = summarise(EVENTS)
    assert s["verdict"]["signal"] == "BUY"
    assert s["signals"][0]["dir"] == "bull"
    assert s["status"] == "completed"
    assert s["duration_ms"] == 1234
```

- [ ] **Step 2: 实现 summarise（纯函数）+ runner 收尾落库**

`persistence.py`：

```python
"""运行摘要折叠与落库。

summarise 是纯函数：事件列表 -> 落库字段。runner 收尾时从 Redis Stream
读全量事件（XRANGE - +）折叠，一次性写库——比边跑边写简单且天然一致。
"""

from __future__ import annotations

from typing import Any

from app.core.logging import logger
from app.schemas.trading_desk import EventType


def summarise(events: list[dict[str, Any]]) -> dict[str, Any]:
    turns: list[dict[str, Any]] = []
    open_turns: dict[str, dict[str, Any]] = {}
    signals: list[dict[str, Any]] = []
    verdict: dict[str, Any] | None = None
    status, duration_ms = "interrupted", 0

    for ev in events:
        t = ev.get("type")
        data = ev.get("data", {})
        if t == "turn.started":
            turn = {
                "turnId": data["turn_id"], "stageId": data.get("stage_id", ""),
                "name": data.get("name", ""), "role": data.get("role", ""),
                "avatar": data.get("avatar", ""), "text": "",
                "human": False, "debate": None, "signal": None,
            }
            open_turns[data["turn_id"]] = turn
            turns.append(turn)
        elif t == "agent.token" and data.get("turn_id") in open_turns:
            open_turns[data["turn_id"]]["text"] += data.get("text", "")
        elif t == "debate.turn":
            turn = open_turns.get(data.get("turn_id"))
            if turn is not None:
                turn["debate"] = {
                    "debateId": data.get("debate_id"), "side": data.get("side"),
                    "sideLabel": data.get("side_label"), "polarity": data.get("polarity"),
                    "round": data.get("round"),
                }
        elif t == "agent.signal":
            signals.append({
                "name": data.get("name"), "dir": data.get("dir"),
                "conf": data.get("conf"), "extracted": data.get("extracted", False),
            })
            turn = open_turns.get(data.get("turn_id"))
            if turn is not None:
                turn["signal"] = {
                    "dir": data.get("dir"), "conf": data.get("conf"),
                    "extracted": data.get("extracted", False),
                }
        elif t == "human.note":
            turns.append({
                "turnId": f"human-{ev.get('seq')}", "stageId": "", "name": "你",
                "role": "人工意见", "avatar": "你", "text": data.get("text", ""),
                "human": True, "debate": None, "signal": None,
                "injectedInto": data.get("injected_into"),
            })
        elif t == "verdict":
            verdict = dict(data)
        elif t == "run.finished":
            status = data.get("status", "interrupted")
            duration_ms = data.get("duration_ms", 0)

    return {
        "turns": turns, "signals": signals, "verdict": verdict,
        "status": status, "duration_ms": duration_ms,
    }


async def persist_run(redis, run_id: str, *, user_id: int, ticker: str,
                      trade_date: str, engine: str) -> None:
    """从 Redis Stream 折叠并落库。失败只记日志——落库失败不应影响用户拿到结果。"""
    from datetime import UTC, datetime

    from app.models.trading_desk_run import TradingDeskRun
    from app.services.trading_desk.event_bus import stream_key
    from app.db.session import get_sync_session, sync_engine  # 按仓库实际同步会话用法调整

    entries = await redis.xrange(stream_key(run_id))
    events = []
    for _, fields in entries:
        raw = fields.get(b"e")
        if raw:
            import json
            events.append(json.loads(raw))
    summary = summarise(events)

    run = TradingDeskRun(
        user_id=user_id, ticker=ticker, trade_date=trade_date, engine=engine,
        status=summary["status"], verdict=summary["verdict"], signals=summary["signals"],
        turns=summary["turns"], duration_ms=summary["duration_ms"],
        finished_at=datetime.now(UTC),
    )
    from sqlmodel import Session
    with Session(sync_engine) as session:
        session.add(run)
        session.commit()
    logger.info("trading_desk_run_persisted", run_id=run_id, status=summary["status"])
```

`runner.py` 的改动：`start_run` 加 `user_id` 参数并透传给 `_execute`；`_execute` 的 `finally` 块里（`clear_control` 之前）调用 `persistence.persist_run(...)`，包在 `try/except` 里防落库失败影响主流程。API 端点 `create_run` 传 `user.id`。

- [ ] **Step 3: 历史端点**

`app/schemas/trading_desk.py` 追加：

```python
class RunBrief(BaseModel):
    run_id: str          # DB 的 UUID 主键转 str
    trade_date: str
    engine: str
    status: str
    verdict_signal: str | None = None
    duration_ms: int = 0
    created_at: str  # ISO


class RunListResponse(BaseResponse):
    runs: list[RunBrief]


class RunDetailResponse(BaseResponse):
    run_id: str
    ticker: str
    trade_date: str
    engine: str
    status: str
    verdict: dict | None = None
    signals: list[dict] = []
    turns: list[dict] = []
    duration_ms: int = 0
    created_at: str
```

`app/api/v1/trading_desk.py` 追加两个端点：`GET /runs`（按 user_id 倒序 50 条，走同步 `sync_engine` 查询——参照仓库现有同步查询用法）与 `GET /runs/{run_id}`（校验属主）。给两个端点写 API 测试（mock Session 或用与现有测试一致的夹具方式；至少测属主校验 404）。

- [ ] **Step 4: 全部测试 + 提交**

```bash
uv run pytest tests/services/trading_desk/ tests/api/ -q
make check
git add -A app/ tests/ alembic/ && git commit -m "feat(trading-desk): 运行落库与历史端点"
```

---

## Task 9: 前端历史与回放

**Files:**
- Modify: `frontend/lib/api/trading_desk.ts`
- Create: `frontend/components/trading_desk/RunHistoryList.tsx`
- Modify: `frontend/app/trading-desk/page.tsx`

- [ ] **Step 1: API 层追加**

```ts
export interface RunBrief {
  run_id: string
  ticker: string
  trade_date: string
  engine: string
  status: string
  verdict_signal: string | null
  duration_ms: number
  created_at: string
}

export interface RunDetail extends RunBrief {
  verdict: Record<string, unknown> | null
  signals: Array<{ name: string; dir: Polarity; conf: number; extracted: boolean }>
  turns: Array<{
    turnId: string
    name: string
    role: string
    avatar: string
    text: string
    human: boolean
    debate: { polarity: Polarity; round: number; sideLabel: string } | null
    signal: { dir: Polarity; conf: number; extracted: boolean } | null
  }>
}

export async function fetchRuns(): Promise<RunBrief[]> {
  const { data } = await apiClient.get<{ runs: RunBrief[] }>('/api/v1/trading-desk/runs')
  return data.runs
}

export async function fetchRunDetail(runId: string): Promise<RunDetail> {
  const { data } = await apiClient.get(`/api/v1/trading-desk/runs/${runId}`)
  return data
}
```

- [ ] **Step 2: RunHistoryList 组件**（历史侧栏：ticker + 日期 + 裁决色点；点击回放）

回放实现：`fetchRunDetail` 后把 `turns/signals/verdict` 直接灌进 store（新增 `loadReplay(detail)` action：构造各状态字段，不经过 applyEvent）。`Turn` 类型与前端 store 的 `Turn` 字段对齐（camelCase 已对齐）。

- [ ] **Step 3: 页面接入**：三栏下方加「历史运行」折叠区，或在左栏底部。点击一条 → `loadReplay` → 三栏渲染完整结果（无流式动画，turn 全文直出——spec §7.2「回放按 turn 直接出全文」）。

- [ ] **Step 4: 检查 + 构建 + 提交推送**

```bash
cd frontend && npx tsc --noEmit && npm run lint && npm run build
git add -A frontend/ && git commit -m "feat(trading-desk/web): 历史与回放" && git push origin master
```

---

## Task 10: 线上验收（真实 LLM 冒烟）

- [ ] **Step 1: 等部署完成**，OpenAPI 确认 `GET /runs`、`GET /runs/{id}` 出现。

- [ ] **Step 2: 用真实 token 跑一次 NVDA**（用户配合或用户自测）：

| 核对项 | 预期 |
|---|---|
| `POST /runs` | run.started 的 engine 为 `tradingagents/0.7.0`，stages 10 个 |
| SSE 流 | 真实中文 token 逐字流出；工具 chip 是真实的 yfinance 工具名 |
| 辩论 | 多/空分轮出现；风控三方（激进/保守/中立）按 polarity 三色 |
| 信号 | 四份 report 各一次 agent.signal，extracted=true |
| 裁决 | signal/confidence 来自真实解析；warning_message 若非空要展示 |
| 暂停/注入 | 状态灯变化；注入的意见出现在流中且影响下游（看 bull researcher 发言是否提及） |
| 完成后 | `GET /runs` 出现该记录；点开可回放 |

- [ ] **Step 3: 发现问题逐个修，验收全过后收尾。**

---

## 验收标准

1. `uv run pytest -m "not slow"` 全绿（新增 ≈25 个测试）
2. `make check` 无新增错误；前端 `tsc`/`lint`/`build` 通过
3. 真实 LLM 跑通完整分析：过程可看、可暂停、可注入、结果可回看
4. 落库记录出现在历史列表，回放直出全文

## 风险与回退

- **真实 LLM 成本**：一次完整 run 数十次调用。验收前先在本地 `TRADING_DESK_ENGINE=tradingagents make dev` 跑一次再上线上冒烟。
- **yfinance 工具在线上环境被墙/限流**：ToolInvocationError 会被 tradingagents 捕获成 `[TOOL_ERROR]` 文本（已见于此前的探针输出），不炸图；但报告质量下降。若普遍失败，二期换 FMP 数据源（spec 已列）。
- **注入后 debate_state 语义漂移**：Task 5 的测试是防线。
