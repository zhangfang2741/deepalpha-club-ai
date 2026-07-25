"""LLM 拍照识别单词服务单元测试（mock llm_service.call，不触网）。"""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.vocabulary.recognizer import (
    RecognitionFailedError,
    RecognizedWord,
    _RecognizeResult,
    enrich_words,
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


async def test_enrich_words_returns_parsed_candidates():
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
    call = AsyncMock(return_value=mock_result)
    with patch("app.services.vocabulary.recognizer.llm_service.call", new=call):
        words = await enrich_words(["resilient", "the"])

    assert len(words) == 1
    assert words[0].word == "resilient"
    # 补释义走纯文本模型（不指定 model_name），不应带图片视觉参数。
    assert call.await_args.kwargs.get("model_name") is None


async def test_enrich_words_returns_empty_without_calling_llm_when_no_words():
    call = AsyncMock()
    with patch("app.services.vocabulary.recognizer.llm_service.call", new=call):
        words = await enrich_words(["", "   "])

    assert words == []
    call.assert_not_awaited()


async def test_enrich_words_raises_on_llm_failure():
    with patch(
        "app.services.vocabulary.recognizer.llm_service.call",
        new=AsyncMock(side_effect=RuntimeError("llm down")),
    ):
        with pytest.raises(RecognitionFailedError):
            await enrich_words(["resilient"])
