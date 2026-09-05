"""AI 解读（daily/deep）测试，mock llm_service.call。"""

from datetime import date, time

from lunar_python import Solar

from app.core.prompts.bazi import DAILY_PROMPT, DEEP_PROMPT
from app.schemas.bazi import InterpretationRequest
from app.services.bazi import interpretation as interpretation_module
from app.services.bazi.interpretation import generate_interpretation


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


async def test_generate_interpretation_daily_uses_daily_prompt(monkeypatch):
    """section="daily" 时应使用 DAILY_PROMPT，且传给 AI 的用户消息包含排盘信息。"""
    captured = {}

    async def fake_call(messages, **kwargs):
        captured["messages"] = messages
        return _FakeMessage("今天适合签约 | 宜：签约 忌：争执")

    monkeypatch.setattr(interpretation_module.llm_service, "call", fake_call)

    request = InterpretationRequest(
        birth_date=date(1990, 5, 15),
        birth_time=time(14, 30, 0),
        birth_city="北京",
        gender="male",
        section="daily",
    )
    result = await generate_interpretation(request)

    assert result.text == "今天适合签约 | 宜：签约 忌：争执"
    system_message, human_message = captured["messages"]
    assert system_message.content == DAILY_PROMPT
    assert "年柱：庚午" in human_message.content
    assert "性别：男" in human_message.content

    today = date.today()
    expected_liu_ri = Solar.fromYmd(today.year, today.month, today.day).getLunar().getDayInGanZhi()
    assert f"今日流日：{expected_liu_ri}" in human_message.content
    assert today.isoformat() in human_message.content


async def test_generate_interpretation_deep_uses_deep_prompt(monkeypatch):
    """section="deep" 时应使用 DEEP_PROMPT，时辰未知时用户消息应体现"时柱：未知"。"""
    captured = {}

    async def fake_call(messages, **kwargs):
        captured["messages"] = messages
        return _FakeMessage("## 性格特质\n...")

    monkeypatch.setattr(interpretation_module.llm_service, "call", fake_call)

    request = InterpretationRequest(
        birth_date=date(1990, 5, 15),
        birth_time=None,
        birth_city="北京",
        gender="female",
        section="deep",
    )
    result = await generate_interpretation(request)

    assert result.text == "## 性格特质\n..."
    system_message, human_message = captured["messages"]
    assert system_message.content == DEEP_PROMPT
    assert "时柱：未知（出生时辰不确定）" in human_message.content
