"""拍照识别 NDJSON 心跳流测试。"""

import asyncio
import json

from app.api.v1.vocabulary.words import _stream_recognition_events
from app.services.vocabulary.recognizer import RecognitionFailedError, RecognizedWord


async def test_stream_emits_heartbeats_until_recognition_completes():
    async def delayed_recognition() -> list[RecognizedWord]:
        await asyncio.sleep(0.03)
        return [
            RecognizedWord(
                word="resilient",
                phonetic_ipa="rɪˈzɪliənt",
                part_of_speech="adj.",
                definition_zh="有韧性的",
            )
        ]

    chunks = [
        json.loads(chunk)
        async for chunk in _stream_recognition_events(
            delayed_recognition(),
            existing_words=set(),
            heartbeat_interval=0.005,
        )
    ]

    assert len([event for event in chunks if event["type"] == "heartbeat"]) >= 2
    assert chunks[-1]["type"] == "result"
    assert chunks[-1]["data"]["candidates"][0]["word"] == "resilient"
    assert chunks[-1]["data"]["candidates"][0]["already_in_library"] is False


async def test_stream_marks_existing_words_in_final_result():
    async def recognition() -> list[RecognizedWord]:
        return [RecognizedWord(word="Known")]

    chunks = [
        json.loads(chunk)
        async for chunk in _stream_recognition_events(
            recognition(),
            existing_words={"known"},
            heartbeat_interval=0.005,
        )
    ]

    result = next(event for event in chunks if event["type"] == "result")
    assert result["data"]["candidates"][0]["already_in_library"] is True


async def test_stream_converts_recognition_failure_to_error_event():
    async def failed_recognition() -> list[RecognizedWord]:
        raise RecognitionFailedError("upstream failed")

    chunks = [
        json.loads(chunk)
        async for chunk in _stream_recognition_events(
            failed_recognition(),
            existing_words=set(),
            heartbeat_interval=0.005,
        )
    ]

    assert chunks[-1] == {"type": "error", "message": "识别失败，请重新拍摄"}
