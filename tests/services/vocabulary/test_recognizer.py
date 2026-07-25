"""LLM 拍照识别单词服务单元测试（mock llm_service.call，不触网）。"""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.vocabulary.recognizer import (
    RecognitionFailedError,
    RecognizedWord,
    _build_recognize_prompt,
    _RecognizeResult,
    recognize_words_from_image,
)


async def test_recognize_words_returns_parsed_candidates():
    mock_result = _RecognizeResult(
        words=[
            RecognizedWord(
                word="resilient",
                phonetic_ipa="rɪˈzɪliənt",
                part_of_speech="adj.",
                definition_zh="有韧性的",
            )
        ]
    )
    with patch(
        "app.services.vocabulary.recognizer.llm_service.call",
        new=AsyncMock(return_value=mock_result),
    ):
        words = await recognize_words_from_image(b"fake-image-bytes")

    assert len(words) == 1
    assert words[0].word == "resilient"
    assert words[0].phonetic_ipa == "rɪˈzɪliənt"
    assert words[0].part_of_speech == "adj."


async def test_recognize_words_returns_empty_list_when_no_words_found():
    with patch(
        "app.services.vocabulary.recognizer.llm_service.call",
        new=AsyncMock(return_value=_RecognizeResult(words=[])),
    ):
        words = await recognize_words_from_image(b"fake-image-bytes")

    assert words == []


async def test_recognize_words_raises_on_llm_failure():
    with patch(
        "app.services.vocabulary.recognizer.llm_service.call",
        new=AsyncMock(side_effect=RuntimeError("llm down")),
    ):
        with pytest.raises(RecognitionFailedError):
            await recognize_words_from_image(b"fake-image-bytes")


def test_build_recognize_prompt_without_hint_is_base_prompt():
    from app.services.vocabulary.recognizer import _RECOGNIZE_PROMPT

    # 无 OCR 线索（None / 空 / 全空白）时退化为纯看图识别的基础 prompt。
    assert _build_recognize_prompt(None) == _RECOGNIZE_PROMPT
    assert _build_recognize_prompt([]) == _RECOGNIZE_PROMPT
    assert _build_recognize_prompt(["", "  "]) == _RECOGNIZE_PROMPT


def test_build_recognize_prompt_appends_hint_words():
    prompt = _build_recognize_prompt(["resilient", " ", "serendipity"])
    # 过滤空白后把候选词拼进去，并保留「综合取并集」的指令。
    assert "resilient, serendipity" in prompt
    assert "综合取并集" in prompt


def test_recognize_prompt_states_proper_noun_and_compound_rules():
    prompt = _build_recognize_prompt(None)
    # 专有名词排除规则。
    assert "专有名词" in prompt
    assert "Google" in prompt and "TikTok" in prompt
    # 连字符复合词整体收录、空格词组拆成实义词。
    assert "e-commerce" in prompt
    assert "拆" in prompt


def test_ocr_hint_reasserts_exclusion_rules_after_union():
    prompt = _build_recognize_prompt(["Google", "the", "engine"])
    # 并集之后，排除规则（含专有名词）仍然适用，避免 OCR 线索把 Google 强行带回。
    assert "综合取并集" in prompt
    assert "专有名词" in prompt


async def test_recognize_passes_ocr_hint_into_prompt():
    mock_result = _RecognizeResult(words=[RecognizedWord(word="resilient")])
    call = AsyncMock(return_value=mock_result)
    with patch("app.services.vocabulary.recognizer.llm_service.call", new=call):
        await recognize_words_from_image(b"fake-image-bytes", ocr_hint=["serendipity"])

    # OCR 候选词应出现在发给 LLM 的图文消息的文本块里。
    sent_message = call.await_args.args[0][0]
    text_block = next(part["text"] for part in sent_message.content if part["type"] == "text")
    assert "serendipity" in text_block
