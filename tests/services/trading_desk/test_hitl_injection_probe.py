"""HITL 注入的可行性探针（spec §5.3 的阶段 0 硬门槛）。

验证链路：
  1. 取 TradingAgents 已编译图的 .builder，重新编译并挂上 checkpointer
     与 interrupt_before —— 它自己是裸 compile()，没有中断能力
  2. 跑到 Bull Researcher 之前中断
  3. 用 aupdate_state 把人工意见追加进 news_report
  4. 恢复执行
  5. 断言人工意见确实出现在 Bull Researcher 的最终 prompt 里

第 5 步是关键：写进 situation_summary 是个陷阱（它只用于 BM25 记忆检索，
不进 prompt），本测试确保我们嫁接到了真正会进 prompt 的字段。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="测试用固定回复。"))])

    def bind_tools(self, tools: Any, **kwargs: Any) -> "RecordingFakeLLM":
        """分析师节点会绑定工具；返回自身即可，固定回复不含 tool_calls。"""
        return self


def _read(state_values: Any, field: str) -> str:
    """状态快照可能是 dict 也可能是 AgentState，统一读取。"""
    if isinstance(state_values, dict):
        return str(state_values.get(field, ""))
    return str(getattr(state_values, field, ""))


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
    ta.__dict__["deep_thinking_llm"] = fake  # type: ignore[index]
    ta.__dict__["quick_thinking_llm"] = fake  # type: ignore[index]

    # 重编译：它自己是裸 compile()，既没有 checkpointer 也没有中断点
    compiled = ta.graph.builder.compile(
        checkpointer=InMemorySaver(),
        interrupt_before=AGENT_NODES,
    )

    cfg: Any = {"configurable": {"thread_id": "probe-1"}, "recursion_limit": 150}
    init = ta.propagator.create_initial_state("NVDA", "2026-08-30")

    # 一路自动恢复，直到停在 Bull Researcher 之前
    async for _ in compiled.astream(init, cfg, stream_mode="updates"):
        pass
    state = await compiled.aget_state(cfg)

    guard = 0
    while state.next and state.next[0] != "Bull Researcher":
        guard += 1
        assert guard < 40, f"迟迟走不到 Bull Researcher，当前停在 {state.next}"
        async for _ in compiled.astream(None, cfg, stream_mode="updates"):
            pass
        state = await compiled.aget_state(cfg)

    assert state.next == ("Bull Researcher",), f"未停在预期节点，实际停在 {state.next}"

    # 注入：追加到 news_report 尾部
    current_news = _read(state.values, "news_report")
    await compiled.aupdate_state(cfg, {"news_report": f"{current_news}\n\n---\n{HUMAN_NOTE}"})

    fake.prompts.clear()
    async for _ in compiled.astream(None, cfg, stream_mode="updates"):
        pass

    joined = "\n".join(fake.prompts)
    assert HUMAN_NOTE in joined, (
        "人工意见没有进入下游 prompt —— news_report 不是有效的嫁接点，必须回到 spec §5.3 重新选字段"
    )
