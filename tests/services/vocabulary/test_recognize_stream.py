"""拍照识别 NDJSON 心跳流测试。

`_stream_recognition_events` 接收的不是一个现成的 coroutine，而是一个
"recognition_factory"：`Callable[[on_partial], Coroutine[...]]`。这是因为
`on_partial` 回调要喂给内部的 `asyncio.Queue`，而这个队列只有
`_stream_recognition_events` 自己知道——由它来创建队列、把 `queue.put_nowait`
传给 factory 换来真正的识别 coroutine，才能在识别任务运行期间同时消费队列里
的 partial 快照。
"""

import asyncio
import json

from app.api.v1.vocabulary.words import _stream_recognition_events
from app.services.vocabulary.recognizer import RecognitionFailedError, RecognizedWord


async def test_stream_emits_heartbeats_until_recognition_completes():
    async def delayed_recognition(on_partial) -> list[RecognizedWord]:
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
            delayed_recognition,
            existing_words=set(),
            heartbeat_interval=0.005,
        )
    ]

    assert len([event for event in chunks if event["type"] == "heartbeat"]) >= 2
    assert chunks[-1]["type"] == "result"
    assert chunks[-1]["data"]["candidates"][0]["word"] == "resilient"
    assert chunks[-1]["data"]["candidates"][0]["already_in_library"] is False


async def test_stream_marks_existing_words_in_final_result():
    async def recognition(on_partial) -> list[RecognizedWord]:
        return [RecognizedWord(word="Known")]

    chunks = [
        json.loads(chunk)
        async for chunk in _stream_recognition_events(
            recognition,
            existing_words={"known"},
            heartbeat_interval=0.005,
        )
    ]

    result = next(event for event in chunks if event["type"] == "result")
    assert result["data"]["candidates"][0]["already_in_library"] is True


async def test_stream_converts_recognition_failure_to_error_event():
    async def failed_recognition(on_partial) -> list[RecognizedWord]:
        raise RecognitionFailedError("upstream failed")

    chunks = [
        json.loads(chunk)
        async for chunk in _stream_recognition_events(
            failed_recognition,
            existing_words=set(),
            heartbeat_interval=0.005,
        )
    ]

    assert chunks[-1] == {"type": "error", "message": "识别失败，请重新拍摄"}


async def test_stream_emits_partial_events_before_final_result():
    """识别 coroutine 通过 on_partial 回调推进度，应作为独立事件出现在最终结果之前。

    这是让前端在识别还没跑完时就能先看到已识别出的词的核心行为。
    """

    async def recognition_with_partial(on_partial) -> list[RecognizedWord]:
        on_partial([RecognizedWord(word="idea", definition_zh="想法")])
        await asyncio.sleep(0.01)
        on_partial(
            [
                RecognizedWord(word="idea", definition_zh="想法"),
                RecognizedWord(word="world", definition_zh="世界"),
            ]
        )
        return [
            RecognizedWord(word="idea", definition_zh="想法"),
            RecognizedWord(word="world", definition_zh="世界"),
        ]

    chunks = [
        json.loads(chunk)
        async for chunk in _stream_recognition_events(
            recognition_with_partial,
            existing_words=set(),
            heartbeat_interval=0.005,
        )
    ]

    partial_events = [c for c in chunks if c["type"] == "partial"]
    assert len(partial_events) == 2
    assert [c["word"] for c in partial_events[0]["data"]["candidates"]] == ["idea"]
    assert [c["word"] for c in partial_events[1]["data"]["candidates"]] == ["idea", "world"]
    # partial 都要出现在最终 result 之前。
    assert chunks.index(partial_events[-1]) < chunks.index(
        next(c for c in chunks if c["type"] == "result")
    )
    assert chunks[-1]["type"] == "result"
