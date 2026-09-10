"""生成器：工具循环收敛、结构化输出、写作阶段校验失败重试。"""

import pytest
from unittest.mock import AsyncMock

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables.config import ensure_config

from tests.services.morning_report import test_schema as ts
from app.services.llm.service import llm_service

from app.services.morning_report import generator as gen
from app.services.morning_report.schema import MorningReportContent


def _valid_content() -> MorningReportContent:
    return MorningReportContent.model_validate(ts._valid_content())


class FakeToolResp:
    def __init__(self, tool_calls=None, content=""):
        self.tool_calls = tool_calls or []
        self.content = content


class FakeReconLLM:
    """第一轮调工具，第二轮返回调研笔记。"""

    def __init__(self):
        self.calls = 0
        self.sent_tool_message = False

    async def ainvoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return FakeToolResp(tool_calls=[
                {"name": "search", "args": {"query": "美股 隔夜"}, "id": "call_1"}
            ])
        assert any(getattr(m, "type", "") == "tool" for m in messages), "工具结果必须回传给模型"
        self.sent_tool_message = True
        return FakeToolResp(content="调研笔记：纳指 -1.2%，VIX 18.4…" * 5)

    def bind_tools(self, tools):
        return self


@pytest.mark.asyncio
async def test_recon_runs_tool_loop(monkeypatch):
    async def fake_tool(args):
        return "搜索结果: 新闻若干"

    tools = [type("T", (), {"name": "search", "ainvoke": staticmethod(fake_tool)})()]
    fake = FakeReconLLM()
    monkeypatch.setattr(gen, "build_tools", lambda market: tools)
    monkeypatch.setattr(gen, "_recon_llm", lambda market: fake)
    notes = await gen.recon("us", "2026-09-08")
    assert fake.sent_tool_message and "调研笔记" in notes


@pytest.mark.asyncio
async def test_generate_report_returns_content(monkeypatch):
    async def fake_recon(market, trade_date):
        return "调研笔记"

    async def fake_write(notes, market, trade_date):
        return _valid_content()

    monkeypatch.setattr(gen, "recon", fake_recon)
    monkeypatch.setattr(gen, "write", fake_write)
    content, meta = await gen.generate_report("us", "2026-09-08")
    assert content.headline.zh
    assert meta["attempts"] == 1


@pytest.mark.asyncio
async def test_write_retries_on_validation_error(monkeypatch):
    """写作阶段首次输出非法 → 带错误信息重试 → 第二次成功。"""
    content = _valid_content()
    state = {"n": 0}

    class FakeCall:
        def __await__(self):  # 简化：直接返回
            raise NotImplementedError

    async def fake_call(messages, **kwargs):
        state["n"] += 1
        if state["n"] == 1:
            raise ValueError("1 validation error for MorningReportContent")
        return content

    monkeypatch.setattr(llm_service, "call", fake_call)
    result = await gen.write("notes", "us", "2026-09-08")
    assert state["n"] == 2 and result.headline.zh


def test_build_tools_us_includes_yfinance_fallback():
    """FMP quote 端点额度/订阅受限时，us 市场必须有不依赖 FMP 的行情兜底工具。"""
    tools = gen.build_tools("us")
    names = [t.name for t in tools]
    assert "us_index_snapshot" in names


def test_morning_report_llm_uses_dedicated_openai_when_configured(monkeypatch):
    """配置 MORNING_REPORT_OPENAI_API_KEY 后必须用独立 OpenAI 实例，不能碰全局 registry。

    晨报要求内容质量高，用户提供了专用 key，只给这个模块用——不能和聊天 Agent/
    供应链/因子探索共用全局默认模型，也不该受 DEFAULT_LLM_MODEL 变化影响。
    """
    captured = {}

    class FakeChatOpenAI:
        def __init__(self, model, api_key, **kwargs):
            captured["model"] = model
            captured["api_key"] = api_key.get_secret_value()

    monkeypatch.setattr(gen.settings, "MORNING_REPORT_OPENAI_API_KEY", "sk-test-dedicated-key")
    monkeypatch.setattr(gen.settings, "MORNING_REPORT_OPENAI_MODEL", "gpt-4o")
    monkeypatch.setattr("langchain_openai.ChatOpenAI", FakeChatOpenAI)

    def boom():
        raise AssertionError("配置了专用 key 时不该碰全局 registry")

    monkeypatch.setattr(gen.llm_registry, "get_default", boom)

    gen._morning_report_llm()
    assert captured == {"model": "gpt-4o", "api_key": "sk-test-dedicated-key"}


def test_morning_report_llm_falls_back_to_global_default_when_not_configured(monkeypatch):
    """未配置专用 key 时必须保持原有行为：直接用全局默认模型，不做任何改动。"""
    monkeypatch.setattr(gen.settings, "MORNING_REPORT_OPENAI_API_KEY", "")
    sentinel = object()
    monkeypatch.setattr(gen.llm_registry, "get_default", lambda: sentinel)
    assert gen._morning_report_llm() is sentinel


@pytest.mark.asyncio
async def test_write_uses_dedicated_openai_model_when_configured(monkeypatch):
    """写作阶段配置了专用 key 时，走独立 OpenAI 实例的结构化输出，不经过 llm_service.call。"""
    content = _valid_content()

    class FakeStructuredLLM:
        async def ainvoke(self, messages):
            return content

    class FakeChatOpenAI:
        def __init__(self, model, api_key, **kwargs):
            pass

        def with_structured_output(self, schema):
            assert schema is MorningReportContent
            return FakeStructuredLLM()

    def boom(*args, **kwargs):
        raise AssertionError("配置了专用 key 时不该走 llm_service.call")

    monkeypatch.setattr(gen.settings, "MORNING_REPORT_OPENAI_API_KEY", "sk-test-dedicated-key")
    monkeypatch.setattr(gen.settings, "MORNING_REPORT_OPENAI_MODEL", "gpt-4o")
    monkeypatch.setattr("langchain_openai.ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(llm_service, "call", boom)

    result = await gen.write("notes", "us", "2026-09-08")
    assert result is content


@pytest.mark.asyncio
async def test_write_raises_when_llm_returns_none(monkeypatch):
    """llm_service.call 静默返回 None（模型未触发结构化输出）时必须报错，不能把 None 当成功返回。

    根因复现：minimax 等模型偶尔不触发 function-calling，LangChain 的
    with_structured_output 会返回 None 而不抛异常；write() 若原样透传，
    下游 `content.model_dump()` 会因 None 崩溃且不落 failed 状态。
    """
    async def fake_call_returns_none(messages, **kwargs):
        return None

    monkeypatch.setattr(llm_service, "call", fake_call_returns_none)
    with pytest.raises(ValueError, match="未返回结构化"):
        await gen.write("notes", "us", "2026-09-08")


@pytest.mark.asyncio
async def test_recon_summarizes_all_results_at_round_limit(monkeypatch):
    """耗尽工具轮次后必须综合全部结果，不能只返回最后一个工具结果。"""
    fake = AsyncMock()
    fake.ainvoke.return_value = FakeToolResp(tool_calls=[
        {"name": "search", "args": {}, "id": "call_1"}
    ])
    summarizer = AsyncMock()
    summarizer.ainvoke.return_value = FakeToolResp(content="完整调研笔记")
    tool = type("T", (), {"name": "search", "ainvoke": AsyncMock(return_value="最后工具结果")})()
    monkeypatch.setattr(gen, "MAX_TOOL_ROUNDS", 2)
    monkeypatch.setattr(gen, "build_tools", lambda _: [tool])
    monkeypatch.setattr(gen, "_recon_llm", lambda _: fake)
    monkeypatch.setattr(gen.llm_registry, "get_default", lambda: summarizer)
    assert await gen.recon("us", "2026-09-08") == "完整调研笔记"
    messages = summarizer.ainvoke.call_args.args[0]
    assert sum(getattr(m, "type", "") == "tool" for m in messages) == 2


@pytest.mark.asyncio
async def test_generation_propagates_trace_context(monkeypatch):
    """两阶段共享追踪上下文，写作服务内部的模型调用也继承回调。"""
    async def fake_recon(market, trade_date):
        config = ensure_config()
        assert config["callbacks"]
        assert config["metadata"]["market"] == market
        return "调研笔记"

    async def fake_write(notes, market, trade_date):
        assert ensure_config()["callbacks"]
        return _valid_content()

    monkeypatch.setattr(gen.settings, "LANGFUSE_TRACING_ENABLED", True)
    monkeypatch.setattr(gen, "langfuse_callback_handler", BaseCallbackHandler())
    monkeypatch.setattr(gen, "recon", fake_recon)
    monkeypatch.setattr(gen, "write", fake_write)
    await gen.generate_report("us", "2026-09-08")
