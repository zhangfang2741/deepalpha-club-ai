"""事件总线读写测试。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.schemas.trading_desk import EventType, RunFinishedData, TokenData, TradingDeskEvent
from app.services.trading_desk import event_bus


def _id_tuple(entry_id: str) -> tuple[int, int]:
    ms, _, seq = entry_id.partition("-")
    return int(ms), int(seq or 0)


class FakeStreamRedis:
    """只实现 XADD / XRANGE / INCR / EXPIRE 的内存替身。

    XRANGE 按真实 Redis 的语义实现为**闭区间**——这一点很重要：若替身
    实现成排他区间，就会掩盖生产代码里「跳过首条」的逻辑错误。
    """

    def __init__(self) -> None:
        self.streams: dict[str, list[tuple[str, dict[bytes, bytes]]]] = {}
        self.counters: dict[str, int] = {}
        self.expires: dict[str, int] = {}
        self._next = 1

    async def xadd(self, key: str, fields: dict[str, Any]) -> bytes:
        entry_id = f"{self._next}-0"
        self._next += 1
        encoded = {k.encode(): (v if isinstance(v, bytes) else str(v).encode()) for k, v in fields.items()}
        self.streams.setdefault(key, []).append((entry_id, encoded))
        return entry_id.encode()

    async def xrange(
        self,
        key: str,
        min: str = "-",  # noqa: A002
        max: str = "+",  # noqa: A002
        count: int | None = None,
    ) -> list[tuple[str, dict[bytes, bytes]]]:
        entries = self.streams.get(key, [])
        if min != "-":
            low = _id_tuple(min)
            entries = [e for e in entries if _id_tuple(e[0]) >= low]
        if max != "+":
            high = _id_tuple(max)
            entries = [e for e in entries if _id_tuple(e[0]) <= high]
        return entries[:count] if count else entries

    async def exists(self, *keys: str) -> int:
        return sum(1 for k in keys if self.streams.get(k) or self.counters.get(k) is not None)

    async def incr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key: str, ttl: int) -> bool:
        self.expires[key] = ttl
        return True


@pytest.fixture
def redis() -> FakeStreamRedis:
    return FakeStreamRedis()


async def test_publish_assigns_monotonic_seq(redis: FakeStreamRedis) -> None:
    for _ in range(3):
        await event_bus.publish(
            redis, "r1", TradingDeskEvent.of("r1", EventType.AGENT_TOKEN, TokenData(turn_id="t", text="x"))
        )

    entries = await redis.xrange(event_bus.stream_key("r1"))
    seqs = [TradingDeskEvent.model_validate_json(fields[b"e"]).seq for _, fields in entries]

    assert seqs == [1, 2, 3]


async def test_publish_sets_ttl_on_stream(redis: FakeStreamRedis) -> None:
    await event_bus.publish(redis, "r1", TradingDeskEvent.of("r1", EventType.STAGE_DONE))

    assert redis.expires[event_bus.stream_key("r1")] > 0
    assert redis.expires[event_bus.seq_key("r1")] > 0


async def test_subscribe_replays_from_beginning(redis: FakeStreamRedis) -> None:
    await event_bus.publish(redis, "r1", TradingDeskEvent.of("r1", EventType.STAGE_ACTIVE))
    await event_bus.publish(
        redis, "r1", TradingDeskEvent.of("r1", EventType.RUN_FINISHED, RunFinishedData(status="completed"))
    )

    received = [ev async for _, ev in event_bus.subscribe(redis, "r1", poll_interval=0)]

    assert [e.type for e in received] == [EventType.STAGE_ACTIVE, EventType.RUN_FINISHED]


async def test_subscribe_resumes_after_last_event_id(redis: FakeStreamRedis) -> None:
    first_id = await event_bus.publish(redis, "r1", TradingDeskEvent.of("r1", EventType.STAGE_ACTIVE))
    await event_bus.publish(
        redis, "r1", TradingDeskEvent.of("r1", EventType.RUN_FINISHED, RunFinishedData(status="completed"))
    )

    received = [ev async for _, ev in event_bus.subscribe(redis, "r1", last_id=first_id, poll_interval=0)]

    assert [e.type for e in received] == [EventType.RUN_FINISHED]


async def test_subscribe_stops_on_fatal_error(redis: FakeStreamRedis) -> None:
    await event_bus.publish(
        redis,
        "r1",
        TradingDeskEvent(type=EventType.ERROR, run_id="r1", data={"message": "boom", "fatal": True}),
    )
    await event_bus.publish(redis, "r1", TradingDeskEvent.of("r1", EventType.STAGE_ACTIVE))

    received = [ev async for _, ev in event_bus.subscribe(redis, "r1", poll_interval=0)]

    assert len(received) == 1
    assert received[0].type is EventType.ERROR


async def test_subscribe_times_out_when_run_never_finishes(redis: FakeStreamRedis) -> None:
    await event_bus.publish(redis, "r1", TradingDeskEvent.of("r1", EventType.STAGE_ACTIVE))

    received = [ev async for _, ev in event_bus.subscribe(redis, "r1", poll_interval=0.01, idle_timeout=0.05)]

    assert [e.type for e in received] == [EventType.STAGE_ACTIVE]


async def test_subscribe_picks_up_events_published_later(redis: FakeStreamRedis) -> None:
    async def publish_later() -> None:
        await asyncio.sleep(0.02)
        await event_bus.publish(
            redis, "r1", TradingDeskEvent.of("r1", EventType.RUN_FINISHED, RunFinishedData(status="completed"))
        )

    task = asyncio.create_task(publish_later())
    received = [ev async for _, ev in event_bus.subscribe(redis, "r1", poll_interval=0.01, idle_timeout=1.0)]
    await task

    assert [e.type for e in received] == [EventType.RUN_FINISHED]


async def test_subscribe_yields_stream_ids_for_reconnect(redis: FakeStreamRedis) -> None:
    await event_bus.publish(redis, "r1", TradingDeskEvent.of("r1", EventType.STAGE_ACTIVE))
    await event_bus.publish(
        redis, "r1", TradingDeskEvent.of("r1", EventType.RUN_FINISHED, RunFinishedData(status="completed"))
    )

    ids = [sid async for sid, _ in event_bus.subscribe(redis, "r1", poll_interval=0)]

    assert len(ids) == 2
    assert all("-" in sid for sid in ids)
