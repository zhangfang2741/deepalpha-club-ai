"""交易台事件协议的形状测试。"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.schemas.trading_desk import (
    EngineCapabilities,
    EventType,
    RunStartedData,
    SignalData,
    StageDescriptor,
    TokenData,
    TradingDeskEvent,
    VerdictData,
)


def test_event_envelope_serialises_to_flat_json() -> None:
    ev = TradingDeskEvent.of(
        run_id="r1",
        type_=EventType.AGENT_TOKEN,
        payload=TokenData(turn_id="t1", text="片段"),
    )
    payload = json.loads(ev.model_dump_json())

    assert payload["type"] == "agent.token"
    assert payload["run_id"] == "r1"
    assert payload["seq"] == 0
    assert payload["data"] == {"turn_id": "t1", "text": "片段"}
    assert isinstance(payload["ts"], int)


def test_run_started_carries_engine_topology() -> None:
    data = RunStartedData(
        ticker="NVDA",
        trade_date="2026-08-30",
        engine="mock/1",
        capabilities=EngineCapabilities(supports_pause=True, supports_inject=True),
        stages=[StageDescriptor(id="s1", name="基本面分析师", role="价值", group="analyst")],
    )
    ev = TradingDeskEvent.of(run_id="r1", type_=EventType.RUN_STARTED, payload=data)

    assert ev.data["stages"][0]["group"] == "analyst"
    assert ev.data["capabilities"]["supports_resume_after_restart"] is False


def test_signal_confidence_is_bounded() -> None:
    with pytest.raises(ValidationError):
        SignalData(stage_id="s1", name="技术面", dir="bull", conf=101)


def test_verdict_matches_trade_recommendation_shape() -> None:
    v = VerdictData(signal="BUY", confidence=0.66, size_fraction=0.04, rationale="理由")

    assert v.warning_message is None
    assert v.target_price is None
    assert v.currency is None


def test_event_can_round_trip() -> None:
    ev = TradingDeskEvent.of(run_id="r1", type_=EventType.STAGE_DONE)
    restored = TradingDeskEvent.model_validate_json(ev.model_dump_json())

    assert restored.type is EventType.STAGE_DONE
    assert restored.data == {}


def test_terminal_events_are_recognised() -> None:
    assert TradingDeskEvent.of("r1", EventType.RUN_FINISHED).is_terminal() is True
    assert TradingDeskEvent.of("r1", EventType.AGENT_TOKEN).is_terminal() is False

    fatal = TradingDeskEvent(type=EventType.ERROR, run_id="r1", data={"message": "x", "fatal": True})
    recoverable = TradingDeskEvent(type=EventType.ERROR, run_id="r1", data={"message": "x", "fatal": False})

    assert fatal.is_terminal() is True
    assert recoverable.is_terminal() is False
