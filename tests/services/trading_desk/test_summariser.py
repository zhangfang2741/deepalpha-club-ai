"""summariser：把事件流折叠成 (verdict, signals, turns) 三元组。"""

from __future__ import annotations

from app.schemas.trading_desk import (
    ConsensusData,
    DebateTurnData,
    ErrorData,
    EventType,
    HumanNoteData,
    RunFinishedData,
    SignalData,
    StageData,
    TokenData,
    ToolCallData,
    TradingDeskEvent,
    TurnDoneData,
    TurnStartedData,
    VerdictData,
)
from app.services.trading_desk.summariser import summarise, summarise_status


def _ev(run_id: str, type_: EventType, payload: object) -> TradingDeskEvent:
    """用 of() 形式构造事件，避免手写 data dict。"""
    return TradingDeskEvent.of(run_id, type_, payload)


def test_summarise_empty_yields_none_and_empty_lists() -> None:
    """空事件流：verdict=None，signals/turns 都空。"""
    v, s, t = summarise([])
    assert v is None
    assert s == []
    assert t == []


def test_summarise_collapses_token_chunks_into_one_turn_text() -> None:
    """TURN_STARTED + 多个 AGENT_TOKEN + TURN_DONE → 一张卡片，text 是拼接结果。"""
    rid = "r1"
    events = [
        _ev(rid, EventType.TURN_STARTED, TurnStartedData(
            turn_id="mkt-1", stage_id="market", name="技术面分析师", role="价格行为", avatar="TA",
        )),
        _ev(rid, EventType.AGENT_TOKEN, TokenData(turn_id="mkt-1", text="回调后")),
        _ev(rid, EventType.AGENT_TOKEN, TokenData(turn_id="mkt-1", text="站稳")),
        _ev(rid, EventType.AGENT_TOOL_CALL, ToolCallData(turn_id="mkt-1", tool="ohlcv.get")),
        _ev(rid, EventType.TURN_DONE, TurnDoneData(turn_id="mkt-1")),
    ]
    _, _, turns = summarise(events)
    assert len(turns) == 1
    assert turns[0]["turn_id"] == "mkt-1"
    assert turns[0]["text"] == "回调后站稳"
    assert turns[0]["tool_calls"] == ["ohlcv.get"]
    assert turns[0]["debate"] is None


def test_summarise_attaches_debate_meta() -> None:
    """DEBATE_TURN 把 round/polarity 写入对应卡片，便于回放页分组。"""
    rid = "r1"
    events = [
        _ev(rid, EventType.TURN_STARTED, TurnStartedData(
            turn_id="bull-r1", stage_id="research_debate", name="多头", role="R1", avatar="BR",
        )),
        _ev(rid, EventType.DEBATE_TURN, DebateTurnData(
            stage_id="research_debate", debate_id="research",
            side="bull", side_label="多头", polarity="bull", round=1, turn_id="bull-r1",
        )),
        _ev(rid, EventType.AGENT_TOKEN, TokenData(turn_id="bull-r1", text="论点")),
        _ev(rid, EventType.TURN_DONE, TurnDoneData(turn_id="bull-r1")),
    ]
    _, _, turns = summarise(events)
    assert turns[0]["debate"] == {
        "debate_id": "research", "side": "bull", "side_label": "多头",
        "polarity": "bull", "round": 1,
    }


def test_summarise_preserves_done_order_not_started_order() -> None:
    """两卡片都收到 STARTED，但谁先 DONE 谁先入列——对应回放阅读节奏。"""
    rid = "r1"
    events = [
        _ev(rid, EventType.TURN_STARTED, TurnStartedData(turn_id="a", stage_id="s", name="A")),
        _ev(rid, EventType.TURN_STARTED, TurnStartedData(turn_id="b", stage_id="s", name="B")),
        _ev(rid, EventType.AGENT_TOKEN, TokenData(turn_id="a", text="aa")),
        _ev(rid, EventType.TURN_DONE, TurnDoneData(turn_id="a")),
        _ev(rid, EventType.AGENT_TOKEN, TokenData(turn_id="b", text="bb")),
        _ev(rid, EventType.TURN_DONE, TurnDoneData(turn_id="b")),
    ]
    _, _, turns = summarise(events)
    assert [t["turn_id"] for t in turns] == ["a", "b"]


def test_summarise_collects_signals_and_verdict() -> None:
    """Signals 按发生顺序收，verdict 单条覆盖式收。"""
    rid = "r1"
    events = [
        _ev(rid, EventType.AGENT_SIGNAL, SignalData(
            stage_id="market", name="技术面", dir="bull", conf=64, turn_id="mkt-1",
        )),
        _ev(rid, EventType.AGENT_SIGNAL, SignalData(
            stage_id="fundamentals", name="基本面", dir="neutral", conf=55, turn_id="fa-1",
        )),
        _ev(rid, EventType.VERDICT, VerdictData(signal="BUY", confidence=0.66)),
    ]
    v, s, _ = summarise(events)
    assert v == v and v["signal"] == "BUY"  # type: ignore[index]
    assert [sig["dir"] for sig in s] == ["bull", "neutral"]
    assert s[0]["conf"] == 64


def test_summarise_drops_unrelated_event_types() -> None:
    """STAGE/CONSENSUS/HUMAN_NOTE/ERROR 不进入摘要字段（它们走别的展示路径）。"""
    rid = "r1"
    events = [
        _ev(rid, EventType.STAGE_ACTIVE, StageData(stage_id="market")),
        _ev(rid, EventType.STAGE_DONE, StageData(stage_id="market")),
        _ev(rid, EventType.CONSENSUS_UPDATE, ConsensusData(bull=2, neutral=1, bear=0, lean="明显偏多")),
        _ev(rid, EventType.HUMAN_NOTE, HumanNoteData(text="调整一下", injected_into="news_report")),
        _ev(rid, EventType.ERROR, ErrorData(message="boom", fatal=False)),
    ]
    v, s, t = summarise(events)
    assert v is None and s == [] and t == []


def test_summarise_includes_unfinished_turns_on_truncated_run() -> None:
    """RUN_FINISHED 提前到达时，未收尾的 turn 也要进 turns，避免回放空白。"""
    rid = "r1"
    events = [
        _ev(rid, EventType.TURN_STARTED, TurnStartedData(turn_id="mkt-1", stage_id="market", name="技术面")),
        _ev(rid, EventType.AGENT_TOKEN, TokenData(turn_id="mkt-1", text="写了一半")),
        # 没有 TURN_DONE，直接 RUN_FINISHED —— 模拟进程中断
        _ev(rid, EventType.RUN_FINISHED, RunFinishedData(status="interrupted")),
    ]
    _, _, turns = summarise(events)
    assert len(turns) == 1
    assert turns[0]["turn_id"] == "mkt-1"
    assert turns[0]["text"] == "写了一半"


def test_summarise_status_completed_when_verdict_seen() -> None:
    assert summarise_status([
        _ev("r", EventType.VERDICT, VerdictData(signal="BUY", confidence=0.5)),
    ]) == "completed"


def test_summarise_status_failed_when_fatal_error() -> None:
    assert summarise_status([
        _ev("r", EventType.ERROR, ErrorData(message="boom", fatal=True)),
    ]) == "failed"


def test_summarise_status_picks_finished_when_no_verdict_or_fatal() -> None:
    assert summarise_status([
        _ev("r", EventType.RUN_FINISHED, RunFinishedData(status="cancelled")),
    ]) == "cancelled"


def test_summarise_status_defaults_to_interrupted_for_empty() -> None:
    assert summarise_status([]) == "interrupted"