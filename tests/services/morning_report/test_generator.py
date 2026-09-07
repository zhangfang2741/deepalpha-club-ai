"""生成器：工具循环收敛、结构化输出、写作阶段校验失败重试。"""

import pytest

from app.services.morning_report import generator as gen
from app.services.morning_report.schema import MorningReportContent


def _valid_content() -> MorningReportContent:
    import tests.services.morning_report.test_schema as ts

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
    from app.services.llm.service import llm_service

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
