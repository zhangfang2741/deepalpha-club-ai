"""公司基础介绍服务测试：FMP 英文原文 + LLM 中文翻译。"""

import json

import pytest
from langchain_core.messages import AIMessage

from app.services.sec_filings import basic_intro


class _StubRedis:
    """内存 Redis 替身：只实现所需的 get/set。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex=None):
        self.store[key] = value


def _fmp_row(**overrides):
    row = {
        "symbol": "AAPL",
        "companyName": "Apple Inc.",
        "industry": "Consumer Electronics",
        "sector": "Technology",
        "ceo": "Tim Cook",
        "website": "https://www.apple.com",
        "fullTimeEmployees": "164000",
        "ipoDate": "1980-12-12",
        "description": "Apple Inc. designs and sells consumer electronics.",
    }
    row.update(overrides)
    return row


def test_contains_cjk():
    assert basic_intro._contains_cjk("苹果公司设计并销售消费电子产品。")
    assert not basic_intro._contains_cjk("Apple Inc. designs consumer electronics.")


def test_extract_message_text_skips_thinking_blocks():
    content = [
        {"type": "thinking", "thinking": "let me translate"},
        {"type": "text", "text": "苹果公司设计并销售消费电子产品。"},
    ]
    assert basic_intro._extract_message_text(content) == "苹果公司设计并销售消费电子产品。"


@pytest.mark.asyncio
async def test_get_basic_intro_translates_and_caches(monkeypatch):
    """英文数据来自 FMP，中文来自 LLM 翻译，成功后写入缓存。"""

    async def fake_get_profile(ticker):
        assert ticker == "AAPL"
        return [_fmp_row()]

    async def fake_call(messages, **kwargs):
        human = messages[-1].content
        assert "Apple Inc. designs" in human
        return AIMessage(content="苹果公司设计并销售消费电子产品。")

    monkeypatch.setattr(basic_intro.fmp_client, "get_company_profile", fake_get_profile)
    monkeypatch.setattr(basic_intro.llm_service, "call", fake_call)

    redis = _StubRedis()
    result = await basic_intro.get_basic_intro("AAPL", redis)

    assert result["ticker"] == "AAPL"
    assert result["name"] == "Apple Inc."
    assert result["description_en"] == "Apple Inc. designs and sells consumer electronics."
    assert result["description_zh"] == "苹果公司设计并销售消费电子产品。"

    cached = json.loads(redis.store[basic_intro._cache_key("AAPL")])
    assert cached == result


@pytest.mark.asyncio
async def test_get_basic_intro_normalizes_symbol_for_fmp(monkeypatch):
    """A 股/港股代码转换成 FMP 要的形态（600519 -> 600519.SS）。"""

    async def fake_get_profile(ticker):
        assert ticker == "600519.SS"
        return [_fmp_row(symbol="600519.SS", companyName="Kweichow Moutai Co., Ltd.")]

    async def fake_call(messages, **kwargs):
        return AIMessage(content="贵州茅台简介。")

    monkeypatch.setattr(basic_intro.fmp_client, "get_company_profile", fake_get_profile)
    monkeypatch.setattr(basic_intro.llm_service, "call", fake_call)

    result = await basic_intro.get_basic_intro("600519", None)
    assert result["ticker"] == "600519.SS"


@pytest.mark.asyncio
async def test_get_basic_intro_cache_hit_skips_fmp_and_llm(monkeypatch):
    """命中缓存时不再调用 FMP / LLM。"""

    async def boom_profile(ticker):
        raise AssertionError("不应调用 FMP")

    async def boom_call(messages, **kwargs):
        raise AssertionError("不应调用 LLM")

    monkeypatch.setattr(basic_intro.fmp_client, "get_company_profile", boom_profile)
    monkeypatch.setattr(basic_intro.llm_service, "call", boom_call)

    redis = _StubRedis()
    cached_value = {"ticker": "AAPL", "name": "Apple Inc.", "industry": "", "sector": "",
                     "ceo": "", "website": "", "employees": "", "ipo_date": "",
                     "description_en": "cached en", "description_zh": "已缓存的中文"}
    redis.store[basic_intro._cache_key("AAPL")] = json.dumps(cached_value, ensure_ascii=False)

    result = await basic_intro.get_basic_intro("AAPL", redis)
    assert result == cached_value


@pytest.mark.asyncio
async def test_get_basic_intro_invalid_symbol_returns_none():
    assert await basic_intro.get_basic_intro("!!!", None) is None


@pytest.mark.asyncio
async def test_get_basic_intro_fmp_empty_returns_none(monkeypatch):
    async def fake_get_profile(ticker):
        return []

    monkeypatch.setattr(basic_intro.fmp_client, "get_company_profile", fake_get_profile)

    assert await basic_intro.get_basic_intro("ZZZZ", None) is None


@pytest.mark.asyncio
async def test_get_basic_intro_translation_failure_still_returns_english(monkeypatch):
    """LLM 调用异常：description_zh 留空，英文数据仍正常返回，且不写缓存。"""

    async def fake_get_profile(ticker):
        return [_fmp_row()]

    async def failing_call(messages, **kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(basic_intro.fmp_client, "get_company_profile", fake_get_profile)
    monkeypatch.setattr(basic_intro.llm_service, "call", failing_call)

    redis = _StubRedis()
    result = await basic_intro.get_basic_intro("AAPL", redis)

    assert result["description_en"] == "Apple Inc. designs and sells consumer electronics."
    assert result["description_zh"] == ""
    assert basic_intro._cache_key("AAPL") not in redis.store


@pytest.mark.asyncio
async def test_get_basic_intro_rejects_untranslated_echo(monkeypatch):
    """模型回显英文原文（未真正翻译）时视为翻译失败：留空、不缓存。"""

    async def fake_get_profile(ticker):
        return [_fmp_row()]

    async def echo_call(messages, **kwargs):
        return AIMessage(content="Apple Inc. designs and sells consumer electronics.")

    monkeypatch.setattr(basic_intro.fmp_client, "get_company_profile", fake_get_profile)
    monkeypatch.setattr(basic_intro.llm_service, "call", echo_call)

    redis = _StubRedis()
    result = await basic_intro.get_basic_intro("AAPL", redis)

    assert result["description_zh"] == ""
    assert basic_intro._cache_key("AAPL") not in redis.store
