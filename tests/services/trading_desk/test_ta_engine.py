"""TradingAgentsEngine 集成测试：假 LLM 跑全图，验证事件协议映射。

只测「内容映射 + 关键时间属性」，HITL 行为单独写在 test_ta_engine_hitl.py 里。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import Field

from app.schemas.trading_desk import EventType
from app.services.trading_desk.engine_base import ControlHandle, RunContext
from app.services.trading_desk.engines.tradingagents import TradingAgentsEngine


class FakeLLM(BaseChatModel):
    """轮流返回不同长度文本的假模型；第 1 次带 tool_call 走一遍工具循环。

    所有分析师共享同一份 bind_tools=self；后续每次 _generate 都被计数，
    这个测试只关心事件链路，不验证报告内容。
    """

    calls: int = Field(default=0)
    prompts: list[str] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        msg = self._next_message(messages)
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs: Any):
        """逐 token 输出。每次调用就是一次 LLM 调用；按 token 切片产生 chunks。"""
        msg = self._next_message(messages)
        chunk = AIMessageChunk(content=msg.content or "")
        if msg.tool_calls:
            chunk = AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {
                        "name": tc["name"],
                        "args": json.dumps(tc["args"]) if isinstance(tc.get("args"), (dict, list)) else str(tc.get("args", "")),
                        "id": tc.get("id", "c1"),
                        "index": idx,
                        "type": "tool_call_chunk",
                    }
                    for idx, tc in enumerate(msg.tool_calls)
                ],
            )
        yield ChatGenerationChunk(message=chunk, generation_info={})
        if msg.content and len(msg.content) > 6:
            # 模拟「分块吐 token」给前端流式观感
            for i in range(6, len(msg.content), 6):
                yield ChatGenerationChunk(message=AIMessageChunk(content=msg.content[i : i + 6]))

    def _next_message(self, messages) -> AIMessage:
        self.calls += 1
        self.prompts.append("\n".join(str(m.content) for m in messages))
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[{"name": "get_stock_data", "args": {"ticker": "NVDA"}, "id": "c1"}],
            )
        return AIMessage(
            content=(
                "FINAL TRANSACTION PROPOSAL: **BUY**\n"
                "```json\n"
                '{"signal": "BUY", "confidence": 0.7, "size_fraction": 0.05,'
                ' "target_price": 200, "stop_loss": 160, "time_horizon_days": 30,'
                ' "rationale": "fake reason"}\n'
                "```"
            )
        )

    def bind_tools(self, tools, **kwargs: Any) -> "FakeLLM":
        return self


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


def _ctx(**kwargs: Any) -> RunContext:
    async def no() -> bool:
        return False

    async def empty() -> list[str]:
        return []

    defaults: dict[str, Any] = dict(
        run_id="r1",
        ticker="NVDA",
        trade_date="2026-08-30",
        control=ControlHandle(is_paused=no, is_cancelled=no, drain_notes=empty),
    )
    defaults.update(kwargs)
    return RunContext(**defaults)


def test_describe_reports_full_topology() -> None:
    """10 个 stage：4 分析师 + 摘要 + 辩论 + 主管 + 交易员 + 风控辩论 + 裁决。

    辩论被合到一张卡片（research_debate / risk_debate），所以是 10 不是 13。
    """
    d = TradingAgentsEngine().describe()

    assert d.engine.startswith("tradingagents")
    assert d.capabilities.supports_pause is True
    assert d.capabilities.supports_inject is True
    ids = [s.id for s in d.stages]
    assert ids[0] == "market_analyst" and ids[-1] == "risk_judge"
    assert len(ids) == 10


@pytest.mark.asyncio
async def test_full_run_emits_protocol_events(tmp_path: Path, fake_llm: FakeLLM) -> None:
    engine = TradingAgentsEngine(
        checkpointer=InMemorySaver(),
        results_dir=tmp_path,
        llm_override=fake_llm,
    )

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

    # 每个 stage 都恰好 active/done 一次
    actives = [e.data["stage_id"] for e in events if e.type is EventType.STAGE_ACTIVE]
    dones = [e.data["stage_id"] for e in events if e.type is EventType.STAGE_DONE]
    assert actives == dones
    assert len(actives) == 10


@pytest.mark.asyncio
async def test_signals_extracted_from_reports(tmp_path: Path, fake_llm: FakeLLM) -> None:
    """四份 analyst report 各跑一次 signal_extract，consensus 实时更新。"""

    class SignalStub:
        async def ainvoke(self, prompt: str) -> str:
            return '{"dir": "bull", "conf": 80}'

    engine = TradingAgentsEngine(
        checkpointer=InMemorySaver(),
        results_dir=tmp_path,
        llm_override=fake_llm,
        extractor_llm=SignalStub(),
    )

    events = [e async for e in engine.astream(_ctx())]

    signals = [e for e in events if e.type is EventType.AGENT_SIGNAL]
    assert len(signals) == 4  # 四份 report
    assert all(s.data["extracted"] is True for s in signals)
    assert all(s.data["dir"] == "bull" for s in signals)

    consensus = [e for e in events if e.type is EventType.CONSENSUS_UPDATE]
    assert consensus[-1].data["lean"] == "明显偏多"
    assert consensus[-1].data["bull"] == 4
