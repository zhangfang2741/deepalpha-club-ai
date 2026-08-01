"""额度用尽时，识别链路必须如实告诉用户，而不是吞成一句「识别失败」。

历史行为：`_call_with_retry` 用 `except Exception` 把一切失败都转成
`RecognitionFailedError`，API 层再统一转成「识别失败，请重新拍摄」。用户看到
的是一句语焉不详的错误，既不知道是额度问题，也不知道重拍没有用。
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.vocabulary.words import _stream_recognition_events
from app.services.llm.service import LLMQuotaExhausted
from app.services.vocabulary.recognizer import (
    RecognitionFailedError,
    RecognitionQuotaExhaustedError,
    recognize_words_from_image,
)

_IMAGE = b"\xff\xd8\xff\xe0fake-jpeg"


async def test_quota_exhaustion_surfaces_as_dedicated_error() -> None:
    """额度用尽要抛专门的异常，不能和「模型抽风」共用一个类型。"""
    quota_error = LLMQuotaExhausted("claude")

    with patch(
        "app.services.vocabulary.recognizer.llm_service.call",
        new=AsyncMock(side_effect=quota_error),
    ):
        with pytest.raises(RecognitionQuotaExhaustedError):
            await recognize_words_from_image(_IMAGE)


async def test_quota_exhaustion_does_not_retry_the_llm() -> None:
    """额度用尽时重试毫无意义，只会让用户多等一轮才看到失败。"""
    mock_call = AsyncMock(side_effect=LLMQuotaExhausted("claude"))

    with patch("app.services.vocabulary.recognizer.llm_service.call", new=mock_call):
        with pytest.raises(RecognitionQuotaExhaustedError):
            await recognize_words_from_image(_IMAGE)

    assert mock_call.await_count == 1


async def test_quota_error_is_still_a_recognition_failure() -> None:
    """保持是 RecognitionFailedError 的子类，既有的兜底捕获不会漏接。"""
    assert issubclass(RecognitionQuotaExhaustedError, RecognitionFailedError)


async def test_stream_reports_quota_message_not_generic_failure() -> None:
    """NDJSON 流要把「额度用完」原样告诉客户端。"""

    async def quota_recognition(on_partial):  # noqa: ANN001, ANN202
        raise RecognitionQuotaExhaustedError("quota exhausted")

    events = [
        json.loads(chunk)
        async for chunk in _stream_recognition_events(
            quota_recognition,
            existing_words=set(),
            heartbeat_interval=0.005,
        )
    ]

    error_events = [event for event in events if event["type"] == "error"]
    assert len(error_events) == 1
    message = error_events[0]["message"]
    assert "额度" in message
    assert "重新拍摄" not in message


async def test_stream_keeps_generic_message_for_ordinary_failures() -> None:
    """非额度类失败的文案不能被这次改动带跑偏——重拍确实可能有用。"""

    async def failing_recognition(on_partial):  # noqa: ANN001, ANN202
        raise RecognitionFailedError("model went sideways")

    events = [
        json.loads(chunk)
        async for chunk in _stream_recognition_events(
            failing_recognition,
            existing_words=set(),
            heartbeat_interval=0.005,
        )
    ]

    error_events = [event for event in events if event["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["message"] == "识别失败，请重新拍摄"
