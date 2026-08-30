"""事件流 → 可落库摘要。

为什么单独建一个模块：
  - 落库只关心「turn 级全文」「按时间顺序的信号」「最终裁决」。
  - 这些都要从逐 token 的事件序列里折叠出来；折叠逻辑留在
    StreamTranslator 会污染翻译器职责（它已经够厚了），留在 runner
    又会让 runner 变成「业务逻辑中心」违背分层规则。
  - 抽到这里后，summarise() 可被测试单独覆盖，runner 只调一行。

设计取舍：events 用「收尾时间序」而不是「开始时间序」输出 turns——
回放页面的卡片布局是按完成时刻串接，先完成的卡先收尾，对应用户的
阅读节奏。如果改成开始序，辩论场景里同一 stage 的多张卡会乱。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.core.logging import logger
from app.schemas.trading_desk import (
    DebateTurnData,
    EventType,
    SignalData,
    TradingDeskEvent,
    TurnStartedData,
    VerdictData,
)


def summarise(events: Iterable[TradingDeskEvent]) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    """折叠一次 run 的事件流，返回 (verdict, signals, turns)。

    Args:
        events: 该 run 的全部事件，按 stream 顺序；通常来自
            StreamTranslator.events 或直接由 Redis Stream 重放。

    Returns:
        verdict: 最终裁决（可能为 None：运行被打断或尚未产出）。
        signals: 按发生顺序的结构化信号列表（SignalData.dump()）。
        turns: 按 turn_done 顺序的卡片列表，每张含 turn_id/stage_id/name
            /role/avatar/text/tool_calls/debate 元数据。
    """
    # turn_id -> 累积中的卡片；收尾后搬到 done_turns（保序）
    open_turns: dict[str, dict[str, Any]] = {}
    done_turns: list[dict[str, Any]] = []

    signals: list[dict[str, Any]] = []
    verdict: dict[str, Any] | None = None

    for event in events:
        t = event.type
        data = event.data

        if t is EventType.TURN_STARTED:
            payload = TurnStartedData.model_validate(data)
            open_turns[payload.turn_id] = {
                "turn_id": payload.turn_id,
                "stage_id": payload.stage_id,
                "name": payload.name,
                "role": payload.role,
                "avatar": payload.avatar,
                "text": "",
                "tool_calls": [],
                "debate": None,
            }
        elif t is EventType.AGENT_TOKEN:
            turn_id = str(data.get("turn_id", ""))
            if turn_id in open_turns:
                open_turns[turn_id]["text"] += str(data.get("text", ""))
            else:
                logger.warning(
                    "trading_desk_summariser_orphan_event",
                    event_type=t.value, turn_id=turn_id, run_id=event.run_id,
                )
        elif t is EventType.AGENT_TOOL_CALL:
            turn_id = str(data.get("turn_id", ""))
            if turn_id in open_turns:
                open_turns[turn_id]["tool_calls"].append(str(data.get("tool", "")))
            else:
                logger.warning(
                    "trading_desk_summariser_orphan_event",
                    event_type=t.value, turn_id=turn_id, run_id=event.run_id,
                )
        elif t is EventType.DEBATE_TURN:
            payload = DebateTurnData.model_validate(data)
            if payload.turn_id in open_turns:
                open_turns[payload.turn_id]["debate"] = {
                    "debate_id": payload.debate_id,
                    "side": payload.side,
                    "side_label": payload.side_label,
                    "polarity": payload.polarity,
                    "round": payload.round,
                }
            else:
                logger.warning(
                    "trading_desk_summariser_orphan_event",
                    event_type=t.value, turn_id=payload.turn_id, run_id=event.run_id,
                )
        elif t is EventType.TURN_DONE:
            turn_id = str(data.get("turn_id", ""))
            if turn_id in open_turns:
                done_turns.append(open_turns.pop(turn_id))
            else:
                logger.warning(
                    "trading_desk_summariser_orphan_event",
                    event_type=t.value, turn_id=turn_id, run_id=event.run_id,
                )
        elif t is EventType.AGENT_SIGNAL:
            signals.append(SignalData.model_validate(data).model_dump(mode="json"))
        elif t is EventType.VERDICT:
            verdict = VerdictData.model_validate(data).model_dump(mode="json")
        else:
            # 未分支的 EventType（STAGE_*/CONSENSUS/HUMAN_NOTE/RUN_*/ERROR 等）：
            # 当前设计不纳入摘要，但记一条 warning，方便后续扩展时定位遗漏。
            logger.warning(
                "trading_desk_summariser_unhandled_event",
                event_type=t.value, run_id=event.run_id,
            )

    # 兜底：被 RUN_FINISHED 截断时，仍把没收尾的 turn 也纳入（避免回放空白）
    for leftover in open_turns.values():
        done_turns.append(leftover)

    return verdict, signals, done_turns


def summarise_status(events: Iterable[TradingDeskEvent]) -> str:
    """从事件序列里推断 run 终止状态，与 RunFinishedData.status 对齐。

    优先级：VERDICT → 出现 ERROR(fatal) → 出现 RUN_FINISHED(status=*) →
    出现 RUN_FINISHED(status=interrupted)。如果都没有，认为是 running。
    """
    verdict_seen = False
    finished_status: str | None = None
    fatal = False

    for event in events:
        if event.type is EventType.VERDICT:
            verdict_seen = True
        elif event.type is EventType.ERROR and bool(event.data.get("fatal")):
            fatal = True
        elif event.type is EventType.RUN_FINISHED:
            finished_status = str(event.data.get("status", "interrupted"))

    if verdict_seen:
        return "completed"
    if fatal:
        return "failed"
    if finished_status is not None:
        return finished_status
    return "interrupted"