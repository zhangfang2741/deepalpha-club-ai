"""Deep Agent 图的流式与序列化测试（使用假模型 + 内存检查点，无需 DB / 网络）。"""

import json
from typing import Any, Optional

import pytest
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from deepagents import create_deep_agent

from app.core.langgraph.graph import LangGraphAgent, _inject_dynamic_context
from app.core.prompts import build_dynamic_context, load_deep_agent_prompt
from app.schemas import Message


@tool
def echo(text: str) -> str:
    """回显传入的文本。

    Args:
        text: 要回显的文本。

    Returns:
        回显结果。
    """
    return f"echoed:{text}"


class _ScriptedModel(BaseChatModel):
    """按脚本依次返回消息的假模型，支持 bind_tools，且不实现流式（走 invoke 回退）。"""

    responses: list[AIMessage] = []
    _idx: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted-fake"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "BaseChatModel":  # noqa: D102
        return self

    def _next(self) -> AIMessage:
        msg = self.responses[min(self._idx, len(self.responses) - 1)]
        object.__setattr__(self, "_idx", self._idx + 1)
        return msg

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._next())])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._next())])


def _make_agent_with_fake_graph() -> LangGraphAgent:
    """构造一个 LangGraphAgent，并把其内部图替换为使用假模型 + 内存检查点的 Deep Agent。"""
    model = _ScriptedModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "call_1", "type": "tool_call"}],
            ),
            AIMessage(content="最终答复：已完成。"),
        ]
    )
    graph = create_deep_agent(
        model=model,
        tools=[echo],
        system_prompt=load_deep_agent_prompt(),
        middleware=[_inject_dynamic_context],
        checkpointer=InMemorySaver(),
    )
    agent = LangGraphAgent()
    agent._graph = graph
    return agent


@pytest.fixture(autouse=True)
def _no_memory(monkeypatch):
    """屏蔽 mem0 长期记忆的网络调用。"""
    from app.core.langgraph import graph as graph_module

    async def _search(user_id, query):
        return ""

    async def _add(user_id, messages, metadata=None):
        return None

    monkeypatch.setattr(graph_module.memory_service, "search", _search)
    monkeypatch.setattr(graph_module.memory_service, "add", _add)


def test_build_dynamic_context_includes_user_and_memory():
    ctx = build_dynamic_context(username="Alice", long_term_memory="喜欢科技股")
    assert "Alice" in ctx
    assert "喜欢科技股" in ctx
    assert "当前日期与时间" in ctx


async def test_langgraph_stream_emits_tool_call_and_text():
    agent = _make_agent_with_fake_graph()
    events = []
    async for chunk in agent.get_langgraph_stream(
        [Message(role="user", content="分析一下")],
        session_id="test-session-1",
        user_id="u1",
        username="Alice",
    ):
        assert chunk.startswith("data: ")
        payload = json.loads(chunk[len("data: ") :].strip())
        events.append(payload)

    # 至少应产生 messages 事件
    message_events = [e for e in events if e["event"] == "messages"]
    assert message_events, f"未收到 messages 事件: {events}"

    # 收集所有序列化消息，验证出现 echo 工具调用与工具结果
    serialized = [e["data"][0] for e in message_events]
    dumped = json.dumps(serialized, ensure_ascii=False)
    assert "echo" in dumped
    assert "echoed:hi" in dumped or "tool" in dumped

    # 无错误事件
    assert not [e for e in events if e["event"] == "error"], events


async def test_langgraph_history_returns_serialized_messages():
    agent = _make_agent_with_fake_graph()
    # 先跑一轮产生历史
    async for _ in agent.get_langgraph_stream(
        [Message(role="user", content="hi")],
        session_id="test-session-2",
        user_id="u1",
        username="Alice",
    ):
        pass

    history = await agent.get_langgraph_history("test-session-2")
    assert isinstance(history, list)
    assert history, "历史不应为空"
    types = {m.get("type") for m in history}
    assert "human" in types
    assert "ai" in types
