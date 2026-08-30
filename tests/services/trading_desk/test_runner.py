"""runner 生命周期测试：用 MockEngine 跑完整链路，不碰真实 LLM 与真实 Redis。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from app.cache import trading_desk_cache as tdc
from app.schemas.trading_desk import EventType, TradingDeskEvent
from app.services.trading_desk import event_bus, runner
from app.services.trading_desk.engine_base import RunContext
from app.services.trading_desk.engines.mock import MockEngine
from tests.services.trading_desk.test_control_cache import FakeRedis
from tests.services.trading_desk.test_event_bus import FakeStreamRedis


class FakeRedisAll(FakeRedis, FakeStreamRedis):
    """同时具备 hash / list / stream / counter 能力的替身。"""

    def __init__(self) -> None:
        FakeRedis.__init__(self)
        FakeStreamRedis.__init__(self)

    async def delete(self, *keys: str) -> int:
        return await FakeRedis.delete(self, *keys)

    async def expire(self, key: str, ttl: int) -> bool:
        self.expires[key] = ttl
        return True


class BoomEngine:
    """一开跑就抛异常，用于验证失败路径。"""

    name = "boom"

    def describe(self):
        return MockEngine().describe()

    async def astream(self, ctx: RunContext) -> AsyncIterator[TradingDeskEvent]:
        raise RuntimeError("引擎炸了")
        yield  # pragma: no cover —— 让本函数成为异步生成器


@pytest.fixture
def redis() -> FakeRedisAll:
    return FakeRedisAll()


async def _drain(redis: FakeRedisAll, run_id: str) -> list[TradingDeskEvent]:
    return [ev async for _, ev in event_bus.subscribe(redis, run_id, poll_interval=0)]


async def test_run_wraps_engine_stream_with_lifecycle_events(redis: FakeRedisAll) -> None:
    run_id = await runner.start_run(
        redis, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0)
    )
    await runner.wait_for(run_id)

    events = await _drain(redis, run_id)

    assert events[0].type is EventType.RUN_STARTED
    assert events[0].data["ticker"] == "NVDA"
    assert events[0].data["engine"] == "mock/1"
    assert events[-1].type is EventType.RUN_FINISHED
    assert events[-1].data["status"] == "completed"


async def test_verdict_precedes_run_finished(redis: FakeRedisAll) -> None:
    run_id = await runner.start_run(
        redis, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0)
    )
    await runner.wait_for(run_id)

    types = [e.type for e in await _drain(redis, run_id)]

    assert types.index(EventType.VERDICT) < types.index(EventType.RUN_FINISHED)


async def test_seq_is_monotonic_across_whole_run(redis: FakeRedisAll) -> None:
    run_id = await runner.start_run(
        redis, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0)
    )
    await runner.wait_for(run_id)

    seqs = [e.seq for e in await _drain(redis, run_id)]

    assert seqs == list(range(1, len(seqs) + 1))


async def test_engine_failure_emits_fatal_error_then_finished(redis: FakeRedisAll) -> None:
    run_id = await runner.start_run(redis, ticker="NVDA", trade_date="2026-08-30", engine=BoomEngine())
    await runner.wait_for(run_id)

    # 致命 error 是终止事件，subscribe 会停在它那里；直接读原始流看全貌
    entries = await redis.xrange(event_bus.stream_key(run_id))
    events = [TradingDeskEvent.model_validate_json(f[b"e"]) for _, f in entries]
    errors = [e for e in events if e.type is EventType.ERROR]

    assert len(errors) == 1
    assert errors[0].data["fatal"] is True
    assert "引擎炸了" in errors[0].data["message"]
    assert events[-1].type is EventType.RUN_FINISHED
    assert events[-1].data["status"] == "failed"


async def test_cancel_ends_run_as_cancelled(redis: FakeRedisAll) -> None:
    run_id = await runner.start_run(
        redis, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0.01)
    )
    await asyncio.sleep(0.05)
    await runner.cancel(redis, run_id)
    await runner.wait_for(run_id)

    events = await _drain(redis, run_id)

    assert events[-1].data["status"] == "cancelled"
    assert all(e.type is not EventType.VERDICT for e in events)


async def _wait_for_event(redis: FakeRedisAll, run_id: str, want: EventType, timeout: float = 5.0) -> bool:
    """轮询等待某个事件出现。不猜时序——暂停只在节点边界生效，睡固定时长会 flaky。"""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        entries = await redis.xrange(event_bus.stream_key(run_id))
        if any(TradingDeskEvent.model_validate_json(f[b"e"]).type is want for _, f in entries):
            return True
        await asyncio.sleep(0.01)
    return False


async def test_pause_emits_paused_event_and_resume_continues(redis: FakeRedisAll) -> None:
    run_id = await runner.start_run(
        redis, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0.001)
    )
    await runner.pause(redis, run_id)

    assert await _wait_for_event(redis, run_id, EventType.RUN_PAUSED), "暂停未在节点边界生效"

    await runner.resume(redis, run_id)
    await runner.wait_for(run_id)

    types = [e.type for e in await _drain(redis, run_id)]

    assert EventType.RUN_PAUSED in types
    assert EventType.RUN_RESUMED in types
    assert types.index(EventType.RUN_PAUSED) < types.index(EventType.RUN_RESUMED)
    assert types[-1] is EventType.RUN_FINISHED


async def test_pause_takes_effect_only_at_node_boundaries(redis: FakeRedisAll) -> None:
    """暂停不会把一张卡片的推理拦腰截断：停下时该 turn 一定已经 turn.done。

    这是 spec §5.2 的核心承诺——若暂停能落在 token 中间，用户会看到半句话
    悬在那里，而下游 agent 拿到的也是半截上下文。
    """
    run_id = await runner.start_run(
        redis, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0.001)
    )
    await runner.pause(redis, run_id)
    assert await _wait_for_event(redis, run_id, EventType.RUN_PAUSED)

    # 暂停生效后再等一会儿，确认没有新的 token 继续冒出来
    entries = await redis.xrange(event_bus.stream_key(run_id))
    settled = [TradingDeskEvent.model_validate_json(f[b"e"]) for _, f in entries]
    await asyncio.sleep(0.05)
    entries_after = await redis.xrange(event_bus.stream_key(run_id))

    assert len(entries_after) == len(settled), "暂停后仍在产出事件"

    opened = {e.data["turn_id"] for e in settled if e.type is EventType.TURN_STARTED}
    closed = {e.data["turn_id"] for e in settled if e.type is EventType.TURN_DONE}
    assert opened == closed, "暂停停在了某个 turn 的中间，把推理拦腰截断了"

    await runner.cancel(redis, run_id)
    await runner.wait_for(run_id)


async def test_injected_note_surfaces_as_human_note(redis: FakeRedisAll) -> None:
    run_id = await runner.start_run(
        redis, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0.01)
    )
    await runner.inject(redis, run_id, "把出口管制风险的权重调高")
    await runner.wait_for(run_id)

    notes = [e for e in await _drain(redis, run_id) if e.type is EventType.HUMAN_NOTE]

    assert len(notes) == 1
    assert notes[0].data["text"] == "把出口管制风险的权重调高"


async def test_control_keys_are_cleaned_up_after_run(redis: FakeRedisAll) -> None:
    run_id = await runner.start_run(
        redis, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0)
    )
    await runner.wait_for(run_id)

    assert tdc.control_key(run_id) not in redis.hashes
    # 事件流保留，供断线重连与回看
    assert event_bus.stream_key(run_id) in redis.streams
