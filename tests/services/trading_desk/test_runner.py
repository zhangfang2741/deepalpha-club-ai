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


class _Row:
    """带 __dict__ 的最小 row 替身：runner 既要 add 又要给属性赋值。

    同时支持 ``row["field"]`` 写法，方便测试直接断言落库字段。
    """

    def __init__(self, src: object) -> None:
        for k, v in vars(src).items():
            if not k.startswith("_"):
                setattr(self, k, v)

    def __getitem__(self, key: str) -> object:
        return getattr(self, key)


class FakeDb:
    """最简 async session 替身：runner 只调 init_run + finalize_run 的 commit。"""

    def __init__(self) -> None:
        self.rows: dict[str, _Row] = {}

    async def commit(self) -> None:
        return None

    async def get(self, _model: type, run_id: str) -> _Row | None:
        return self.rows.get(run_id)

    def add(self, obj: object) -> None:
        d = vars(obj)
        run_id = str(d["id"])
        if run_id in self.rows:
            # finalize_run：把字段拷回已存在 row 上（覆盖式更新）
            row = self.rows[run_id]
            for k, v in d.items():
                if not k.startswith("_"):
                    setattr(row, k, v)
        else:
            # init_run：新建 row
            self.rows[run_id] = _Row(obj)


class _FakeDbCM:
    """把 FakeDb 包成 async session context manager。"""

    def __init__(self, db: FakeDb) -> None:
        self._db = db

    async def __aenter__(self) -> FakeDb:
        return self._db

    async def __aexit__(self, *exc: object) -> None:
        return None


def _fake_session_factory(db: FakeDb):  # type: ignore[no-untyped-def]
    """生成一个可 monkeypatch 到 runner.SessionFactory 的可调用对象。"""
    def factory() -> _FakeDbCM:
        return _FakeDbCM(db)
    return factory


class BoomEngine:
    """一开跑就抛异常，用于验证失败路径。"""

    name = "boom"

    def describe(self):
        return MockEngine().describe()

    async def astream(self, ctx: RunContext) -> AsyncIterator[TradingDeskEvent]:
        raise RuntimeError("引擎炸了")
        yield  # pragma: no cover —— 让本函数成为异步生成器


class SlowEngine:
    """不主动产任何 turn，单纯轮询取消标志。被取消前不会结束。"""

    name = "slow"

    def describe(self):
        return MockEngine().describe()

    async def astream(self, ctx: RunContext) -> AsyncIterator[TradingDeskEvent]:
        # 等取消：每隔 ~5ms 检查一次，最多等 2s
        for _ in range(400):
            if await ctx.control.is_cancelled():
                return
            await asyncio.sleep(0.005)
        # 超时也直接结束（避免测试挂死）
        yield  # pragma: no cover —— 让本函数成为异步生成器


@pytest.fixture
def redis() -> FakeRedisAll:
    return FakeRedisAll()


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeDb:
    """提供 FakeDb 并把它塞进 runner.SessionFactory，runner 整段链路都走它。"""
    fake = FakeDb()
    monkeypatch.setattr(runner, "SessionFactory", _fake_session_factory(fake))
    return fake


async def _drain(redis: FakeRedisAll, run_id: str) -> list[TradingDeskEvent]:
    return [ev async for _, ev in event_bus.subscribe(redis, run_id, poll_interval=0)]


async def test_run_wraps_engine_stream_with_lifecycle_events(redis: FakeRedisAll, db: FakeDb) -> None:
    run_id = await runner.start_run(
        redis, user_id=1, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0)
    )
    await runner.wait_for(run_id)

    events = await _drain(redis, run_id)

    assert events[0].type is EventType.RUN_STARTED
    assert events[0].data["ticker"] == "NVDA"
    assert events[0].data["engine"] == "mock/1"
    assert events[-1].type is EventType.RUN_FINISHED
    assert events[-1].data["status"] == "completed"


async def test_event_stream_exists_the_moment_start_run_returns(redis: FakeRedisAll, db: FakeDb) -> None:
    """start_run 一返回，事件流就必须已经存在。

    否则调用方拿到 run_id 后立刻订阅会撞上竞态，SSE 端点会误报 404。
    """
    run_id = await runner.start_run(
        redis, user_id=1, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0)
    )

    assert await event_bus.exists(redis, run_id) is True

    entries = await redis.xrange(event_bus.stream_key(run_id))
    first = TradingDeskEvent.model_validate_json(entries[0][1][b"e"])
    assert first.type is EventType.RUN_STARTED

    await runner.wait_for(run_id)


async def test_exists_is_false_for_unknown_run(redis: FakeRedisAll, db: FakeDb) -> None:
    assert await event_bus.exists(redis, "no-such-run") is False


async def test_verdict_precedes_run_finished(redis: FakeRedisAll, db: FakeDb) -> None:
    run_id = await runner.start_run(
        redis, user_id=1, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0)
    )
    await runner.wait_for(run_id)

    types = [e.type for e in await _drain(redis, run_id)]

    assert types.index(EventType.VERDICT) < types.index(EventType.RUN_FINISHED)


async def test_seq_is_monotonic_across_whole_run(redis: FakeRedisAll, db: FakeDb) -> None:
    run_id = await runner.start_run(
        redis, user_id=1, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0)
    )
    await runner.wait_for(run_id)

    seqs = [e.seq for e in await _drain(redis, run_id)]

    assert seqs == list(range(1, len(seqs) + 1))


async def test_engine_failure_emits_fatal_error_then_finished(redis: FakeRedisAll, db: FakeDb) -> None:
    run_id = await runner.start_run(redis, user_id=1, ticker="NVDA", trade_date="2026-08-30", engine=BoomEngine())
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


async def test_cancel_ends_run_as_cancelled(redis: FakeRedisAll, db: FakeDb) -> None:
    run_id = await runner.start_run(
        redis, user_id=1, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0.01)
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


async def test_pause_emits_paused_event_and_resume_continues(redis: FakeRedisAll, db: FakeDb) -> None:
    run_id = await runner.start_run(
        redis, user_id=1, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0.001)
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


async def test_pause_takes_effect_only_at_node_boundaries(redis: FakeRedisAll, db: FakeDb) -> None:
    """暂停不会把一张卡片的推理拦腰截断：停下时该 turn 一定已经 turn.done。

    这是 spec §5.2 的核心承诺——若暂停能落在 token 中间，用户会看到半句话
    悬在那里，而下游 agent 拿到的也是半截上下文。
    """
    run_id = await runner.start_run(
        redis, user_id=1, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0.001)
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


async def test_injected_note_surfaces_as_human_note(redis: FakeRedisAll, db: FakeDb) -> None:
    run_id = await runner.start_run(
        redis, user_id=1, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0.01)
    )
    await runner.inject(redis, run_id, "把出口管制风险的权重调高")
    await runner.wait_for(run_id)

    notes = [e for e in await _drain(redis, run_id) if e.type is EventType.HUMAN_NOTE]

    assert len(notes) == 1
    assert notes[0].data["text"] == "把出口管制风险的权重调高"


async def test_control_keys_are_cleaned_up_after_run(redis: FakeRedisAll, db: FakeDb) -> None:
    run_id = await runner.start_run(
        redis, user_id=1, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0)
    )
    await runner.wait_for(run_id)

    assert tdc.control_key(run_id) not in redis.hashes
    # 事件流保留，供断线重连与回看
    assert event_bus.stream_key(run_id) in redis.streams


async def test_run_persists_row_with_status_and_summary(redis: FakeRedisAll, db: FakeDb) -> None:
    """一次正常跑完之后，TradingDeskRun 行要被 finalize 成 completed 且含 verdict/turns。

    验证 runner 的持久化集成：init_run（占位） + finalize_run（收尾摘要）。
    FakeDb 用 dict 替身承载，便于直接断言落库字段。
    """
    run_id = await runner.start_run(
        redis, user_id=42, ticker="NVDA", trade_date="2026-08-30", engine=MockEngine(tick_seconds=0)
    )
    # init_run 已经写过一行：status=running、engine=mock/1
    assert run_id in db.rows
    assert db.rows[run_id]["status"] == "running"
    assert db.rows[run_id]["engine"] == "mock/1"
    assert db.rows[run_id]["user_id"] == 42

    await runner.wait_for(run_id)

    row = db.rows[run_id]
    assert row["status"] == "completed"
    assert int(row["duration_ms"]) >= 0  # type: ignore[arg-type]
    assert row["finished_at"] is not None
    # verdict/turns 由 summarise() 折叠出来
    verdict = row["verdict"]
    assert isinstance(verdict, dict) and verdict["signal"] == "BUY"  # type: ignore[index]
    turns = row["turns"]
    assert isinstance(turns, list) and len(turns) > 0  # type: ignore[arg-type]
    signals = row["signals"]
    assert isinstance(signals, list) and len(signals) > 0  # type: ignore[arg-type]


async def test_failed_run_persists_failed_status(redis: FakeRedisAll, db: FakeDb) -> None:
    """引擎抛致命异常 → 行被 finalize 成 failed，verdict/turns 允许为空。"""
    run_id = await runner.start_run(
        redis, user_id=1, ticker="NVDA", trade_date="2026-08-30", engine=BoomEngine()
    )
    await runner.wait_for(run_id)

    row = db.rows[run_id]
    assert row["status"] == "failed"
    assert row["verdict"] is None  # 没跑到 verdict 阶段


async def test_cancelled_run_persists_cancelled_status(redis: FakeRedisAll, db: FakeDb) -> None:
    """中途调 cancel() → 行被 finalize 成 cancelled，duration_ms >= 0。"""
    run_id = await runner.start_run(
        redis, user_id=1, ticker="NVDA", trade_date="2026-08-30", engine=SlowEngine(),
    )
    # 给背景任务一拍进入 astream，再发取消
    await asyncio.sleep(0.02)
    await runner.cancel(redis, run_id)
    await runner.wait_for(run_id)

    row = db.rows[run_id]
    assert row["status"] == "cancelled"
    assert row["finished_at"] is not None
    assert int(row["duration_ms"]) >= 0  # type: ignore[arg-type]
