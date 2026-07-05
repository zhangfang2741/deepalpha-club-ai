"""财报电话会议 AI 总结与翻译服务测试。"""

import pytest
from langchain_core.messages import AIMessage

from app.schemas.motley_fool import TranscriptSummary, TranscriptTranslationResponse
from app.services import transcript_ai
from app.services.transcript_ai import (
    TranscriptAIService,
    _contains_cjk,
    _extract_message_text,
    _split_into_chunks,
    transcript_ai_service,
)


def test_split_into_chunks_respects_max_chars():
    """按段落切分且每块不超过上限。"""
    paragraphs = ["段落" * 200 for _ in range(5)]
    text = "\n\n".join(paragraphs)
    chunks = _split_into_chunks(text, max_chars=500)
    assert len(chunks) >= 2
    assert all(len(chunk) <= 500 or "\n\n" not in chunk for chunk in chunks)


def test_split_into_chunks_splits_oversized_paragraph():
    """单个超长段落会被进一步切分。"""
    long_paragraph = ". ".join(f"sentence number {i}" for i in range(200))
    chunks = _split_into_chunks(long_paragraph, max_chars=200)
    assert len(chunks) >= 2
    assert all(len(chunk) <= 400 for chunk in chunks)


def test_split_into_chunks_empty():
    """空文本返回空列表。"""
    assert _split_into_chunks("", max_chars=100) == []


def test_extract_message_text_plain_string():
    """字符串内容直接返回。"""
    assert _extract_message_text("  你好  ") == "你好"


def test_extract_message_text_skips_thinking_blocks():
    """Claude extended thinking：只取 text 块，丢弃 thinking / signature。"""
    content = [
        {"type": "thinking", "thinking": "Let me translate...", "signature": "abc123"},
        {"type": "text", "text": "英伟达本季营收强劲增长。"},
    ]
    result = _extract_message_text(content)
    assert result == "英伟达本季营收强劲增长。"
    assert "thinking" not in result
    assert "signature" not in result


def test_extract_message_text_joins_multiple_text_blocks():
    """多个 text 块按顺序拼接。"""
    content = [
        {"type": "text", "text": "第一段"},
        {"type": "reasoning", "text": "内部推理，应丢弃"},
        {"type": "text", "text": "第二段"},
    ]
    assert _extract_message_text(content) == "第一段\n第二段"


class _StubCache:
    """内存缓存桩，记录 set 调用。"""

    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ttl=None):
        self.store[key] = value


@pytest.mark.asyncio
async def test_summarize_calls_llm_and_caches(monkeypatch):
    """总结：调用 LLM 并写入缓存，命中缓存时不再调用 LLM。"""
    cache = _StubCache()
    monkeypatch.setattr(transcript_ai, "cache_service", cache)

    call_count = 0

    async def fake_call(messages, response_format=None, **kwargs):
        nonlocal call_count
        call_count += 1
        assert response_format is TranscriptSummary
        # 总结走放宽的超时预算，避免频繁超时
        assert kwargs.get("timeout") == transcript_ai._SUMMARY_LLM_TIMEOUT_SECONDS
        return TranscriptSummary(
            overview="英伟达本季营收强劲增长",
            key_points=["数据中心需求旺盛"],
            financial_highlights=["营收同比增长"],
            guidance="预计下季继续增长",
            qa_highlights=["分析师关注供给"],
            risks=["供应链风险"],
        )

    monkeypatch.setattr(transcript_ai.llm_service, "call", fake_call)

    service = TranscriptAIService()
    url = "https://www.fool.com/earnings/call-transcripts/2026/05/28/nvda/"
    first = await service.summarize("NVDA", "NVDA Q1", url, "prepared text", "qa text")
    assert first.summary.overview == "英伟达本季营收强劲增长"
    assert call_count == 1

    # 第二次命中缓存，不再调用 LLM
    second = await service.summarize("NVDA", "NVDA Q1", url, "prepared text", "qa text")
    assert second.summary.key_points == ["数据中心需求旺盛"]
    assert call_count == 1


@pytest.mark.asyncio
async def test_translate_chunks_and_joins(monkeypatch):
    """翻译：分段翻译后按顺序拼接，并写入缓存。"""
    cache = _StubCache()
    monkeypatch.setattr(transcript_ai, "cache_service", cache)

    async def fake_call(messages, **kwargs):
        # 回显输入内容前加中文标记，验证拼接顺序
        human = messages[-1].content
        return AIMessage(content=f"【译】{human[:6]}")

    monkeypatch.setattr(transcript_ai.llm_service, "call", fake_call)

    service = TranscriptAIService()
    url = "https://www.fool.com/earnings/call-transcripts/2026/05/28/nvda/"
    prepared = "\n\n".join(f"paragraph {i} " + "x" * 1600 for i in range(3))
    result = await service.translate("NVDA", url, prepared, "question one")

    assert result.prepared_remarks_zh.count("【译】") >= 3
    assert result.questions_and_answers_zh.startswith("【译】")
    # 缓存已写入
    assert cache.store


@pytest.mark.asyncio
async def test_translate_stream_yields_in_order_and_caches(monkeypatch):
    """流式翻译：按 prepared→qa 顺序逐段产出，结束后写缓存。"""
    cache = _StubCache()
    monkeypatch.setattr(transcript_ai, "cache_service", cache)

    async def fake_call(messages, **kwargs):
        human = messages[-1].content
        return AIMessage(content=f"译:{human[:10]}")

    monkeypatch.setattr(transcript_ai.llm_service, "call", fake_call)

    service = TranscriptAIService()
    url = "https://www.fool.com/earnings/call-transcripts/2026/05/28/nvda/"
    prepared = "\n\n".join(f"prep {i} " + "x" * 1600 for i in range(2))
    qa = "\n\n".join(f"qa {i} " + "y" * 1600 for i in range(2))

    events: list[tuple[str, str]] = []
    async for section, text in service.translate_stream("NVDA", url, prepared, qa):
        events.append((section, text))

    sections = [section for section, _ in events]
    # prepared 段全部先于 qa 段产出
    assert sections == ["prepared_remarks", "prepared_remarks", "questions_and_answers", "questions_and_answers"]
    assert all(text.startswith("译:") for _, text in events)
    # 结束后写入缓存
    assert cache.store


@pytest.mark.asyncio
async def test_translate_stream_uses_cache(monkeypatch):
    """流式翻译命中缓存时不再调用 LLM。"""
    cache = _StubCache()
    url = "https://www.fool.com/earnings/call-transcripts/2026/05/28/nvda/"
    from app.services.transcript_ai import _TRANSLATION_CACHE_KIND, _cache_key

    cache.store[_cache_key(_TRANSLATION_CACHE_KIND, url)] = TranscriptTranslationResponse(
        ticker="NVDA", url=url, prepared_remarks_zh="缓存的管理层发言", questions_and_answers_zh="缓存的问答"
    ).model_dump_json()
    monkeypatch.setattr(transcript_ai, "cache_service", cache)

    called = False

    async def fake_call(messages, **kwargs):
        nonlocal called
        called = True
        return AIMessage(content="不应被调用")

    monkeypatch.setattr(transcript_ai.llm_service, "call", fake_call)

    service = TranscriptAIService()
    events = [item async for item in service.translate_stream("NVDA", url, "prep", "qa")]
    assert ("prepared_remarks", "缓存的管理层发言") in events
    assert ("questions_and_answers", "缓存的问答") in events
    assert called is False


@pytest.mark.asyncio
async def test_translate_chunk_retries_when_output_not_chinese(monkeypatch):
    """模型首次回显英文（无中文）时，用强化指令重试一次并采用中文结果。"""
    cache = _StubCache()
    monkeypatch.setattr(transcript_ai, "cache_service", cache)

    calls: list[str] = []

    async def fake_call(messages, **kwargs):
        human = messages[-1].content
        calls.append(human)
        # 第一次直接回显英文原文（未翻译），第二次（含强化前缀）才给中文
        if human.startswith(transcript_ai._TRANSLATE_REINFORCE_PREFIX):
            return AIMessage(content="这是翻译后的中文内容。")
        return AIMessage(content="This is the original English content unchanged.")

    monkeypatch.setattr(transcript_ai.llm_service, "call", fake_call)

    service = TranscriptAIService()
    url = "https://www.fool.com/earnings/call-transcripts/2026/05/28/nvda/"
    result = await service.translate("NVDA", url, "This is a long english paragraph to translate.", "")

    assert "这是翻译后的中文内容。" in result.prepared_remarks_zh
    # 一次原始 + 一次强化重试
    assert len(calls) == 2
    assert calls[1].startswith(transcript_ai._TRANSLATE_REINFORCE_PREFIX)
    # 译文为中文，允许写缓存
    assert cache.store


@pytest.mark.asyncio
async def test_translate_not_cached_when_still_english(monkeypatch):
    """模型始终回显英文（重试后仍无中文）时，不写缓存，避免污染 7 天。"""
    cache = _StubCache()
    monkeypatch.setattr(transcript_ai, "cache_service", cache)

    async def fake_call(messages, **kwargs):
        return AIMessage(content="Still english after retry, no chinese at all.")

    monkeypatch.setattr(transcript_ai.llm_service, "call", fake_call)

    service = TranscriptAIService()
    url = "https://www.fool.com/earnings/call-transcripts/2026/05/28/nvda/"
    result = await service.translate("NVDA", url, "This is english paragraph to translate now.", "")

    # 全英文结果不写缓存
    assert cache.store == {}
    assert not _contains_cjk(result.prepared_remarks_zh)


@pytest.mark.asyncio
async def test_translate_empty_section(monkeypatch):
    """空章节翻译返回空字符串，不调用 LLM。"""
    cache = _StubCache()
    monkeypatch.setattr(transcript_ai, "cache_service", cache)

    called = False

    async def fake_call(messages, **kwargs):
        nonlocal called
        called = True
        return AIMessage(content="不应被调用")

    monkeypatch.setattr(transcript_ai.llm_service, "call", fake_call)

    result = await transcript_ai_service.translate("NVDA", "", "", "")
    assert result.prepared_remarks_zh == ""
    assert result.questions_and_answers_zh == ""
    assert called is False
