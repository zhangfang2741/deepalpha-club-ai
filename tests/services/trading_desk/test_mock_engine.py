"""MockEngine 行为测试。"""

from __future__ import annotations

from app.schemas.trading_desk import EventType, TradingDeskEvent
from app.services.trading_desk.engine_base import ControlHandle, RunContext
from app.services.trading_desk.engines.mock import MockEngine


def _ctx(
    *,
    ticker: str = "NVDA",
    notes: list[str] | None = None,
    cancelled: bool = False,
) -> RunContext:
    pending_notes = list(notes or [])

    async def is_paused() -> bool:
        return False

    async def is_cancelled() -> bool:
        return cancelled

    async def drain_notes() -> list[str]:
        drained = list(pending_notes)
        pending_notes.clear()
        return drained

    return RunContext(
        run_id="r1",
        ticker=ticker,
        trade_date="2026-08-30",
        control=ControlHandle(is_paused=is_paused, is_cancelled=is_cancelled, drain_notes=drain_notes),
    )


async def _collect(engine: MockEngine, ctx: RunContext) -> list[TradingDeskEvent]:
    return [ev async for ev in engine.astream(ctx)]


def test_describe_reports_topology_and_capabilities() -> None:
    d = MockEngine().describe()

    assert d.capabilities.supports_pause is True
    assert d.capabilities.supports_inject is True
    assert len(d.stages) >= 6
    assert {s.group for s in d.stages} >= {"analyst", "debate", "manager"}


async def test_stream_emits_tokens_debate_and_verdict() -> None:
    events = await _collect(MockEngine(tick_seconds=0), _ctx())
    types = [e.type for e in events]

    assert EventType.AGENT_TOKEN in types
    assert EventType.DEBATE_TURN in types
    assert EventType.AGENT_SIGNAL in types
    assert types[-1] is EventType.VERDICT, "最后一个事件应为裁决；run.finished 由 runner 包裹"


async def test_every_token_belongs_to_an_opened_turn() -> None:
    events = await _collect(MockEngine(tick_seconds=0), _ctx())

    opened: set[str] = set()
    for ev in events:
        if ev.type is EventType.TURN_STARTED:
            opened.add(ev.data["turn_id"])
        if ev.type is EventType.AGENT_TOKEN:
            assert ev.data["turn_id"] in opened, "token 归属到了未开启的 turn"


async def test_stage_lifecycle_is_balanced() -> None:
    events = await _collect(MockEngine(tick_seconds=0), _ctx())

    actives = [e.data["stage_id"] for e in events if e.type is EventType.STAGE_ACTIVE]
    dones = [e.data["stage_id"] for e in events if e.type is EventType.STAGE_DONE]

    assert actives == dones, "每个 stage 都应恰好 active 一次、done 一次，且顺序一致"


async def test_debate_turns_carry_polarity_and_round() -> None:
    events = await _collect(MockEngine(tick_seconds=0), _ctx())
    debates = [e for e in events if e.type is EventType.DEBATE_TURN]

    assert {d.data["polarity"] for d in debates} >= {"bull", "bear"}
    assert max(d.data["round"] for d in debates) >= 2


async def test_consensus_tracks_signals() -> None:
    events = await _collect(MockEngine(tick_seconds=0), _ctx())
    consensus = [e for e in events if e.type is EventType.CONSENSUS_UPDATE]
    signals = [e for e in events if e.type is EventType.AGENT_SIGNAL]

    assert len(consensus) == len(signals), "每产生一个信号就应刷新一次共识"
    last = consensus[-1].data
    assert last["bull"] + last["neutral"] + last["bear"] == len(signals)


async def test_injected_note_becomes_human_note_event() -> None:
    events = await _collect(MockEngine(tick_seconds=0), _ctx(notes=["把出口管制风险的权重调高"]))
    notes = [e for e in events if e.type is EventType.HUMAN_NOTE]

    assert len(notes) == 1
    assert notes[0].data["text"] == "把出口管制风险的权重调高"
    assert notes[0].data["injected_into"] == "news_report"


async def test_cancel_stops_the_stream_early() -> None:
    events = await _collect(MockEngine(tick_seconds=0), _ctx(cancelled=True))

    assert all(e.type is not EventType.VERDICT for e in events)
    assert len(events) < 10


async def test_script_text_is_parameterised_by_ticker() -> None:
    """剧本按 ticker 参数化：输入 FIG 就该看到 FIG，不该看到写死的标的叙事。"""
    events_fig = await _collect(MockEngine(tick_seconds=0), _ctx(ticker="FIG"))
    fig_tokens = "".join(e.data["text"] for e in events_fig if e.type is EventType.AGENT_TOKEN)

    assert "FIG" in fig_tokens
    assert "NVDA" not in fig_tokens, "剧本里出现了写死的标的代码"

    events_aapl = await _collect(MockEngine(tick_seconds=0), _ctx(ticker="AAPL"))
    aapl_tokens_text = "".join(e.data["text"] for e in events_aapl if e.type is EventType.AGENT_TOKEN)
    assert "AAPL" in aapl_tokens_text
    assert fig_tokens != aapl_tokens_text, "不同标的应产出不同文本"
