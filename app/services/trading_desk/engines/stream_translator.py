"""LangGraph 双模式 chunk -> 事件协议 的纯翻译器。

StreamTranslator 是一个有状态的折叠器——引擎把 astream 的 chunk 原样
喂进来，feed() 返回需要外发的事件列表。这样翻译逻辑可以完全脱开
LangGraph 与 Redis 做单元测试。

不在这里做：signal_extract（引擎在 pending_reports 出现时另行调用）、
verdict 解析（引擎在 verdict_text 出现时另行调用）。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessageChunk

from app.schemas.trading_desk import (
    DebateTurnData,
    EventType,
    StageData,
    ToolCallData,
    TokenData,
    TradingDeskEvent,
    TurnDoneData,
    TurnStartedData,
)
from app.services.trading_desk.engines import stage_map

# report 完成检测：updates 里的字段 -> (stage_id, 展示名)
_REPORT_KEYS: dict[str, tuple[str, str]] = {
    "market_report": ("market_analyst", "技术面分析师"),
    "sentiment_report": ("social_analyst", "社交情绪"),
    "news_report": ("news_analyst", "消息与新闻"),
    "fundamentals_report": ("fundamentals_analyst", "基本面分析师"),
}


class StreamTranslator:
    """把 (mode, payload) chunk 折叠成事件。"""

    def __init__(self, run_id: str) -> None:
        """按 run_id 初始化一张全新折叠器；每次 run 实例化一个。

        状态字段含义见下方属性约定。
        """
        self.run_id = run_id
        self.events: list[TradingDeskEvent] = []
        self._current_turn: dict[str, str] = {}      # node -> turn_id（本轮未完结的）
        self._turn_text: dict[str, list[str]] = {}   # turn_id -> token 片段
        self._node_runs: dict[str, int] = {}         # node -> 完成次数
        self._last_turns: dict[str, str] = {}        # node -> 最近收尾的 turn_id
        self._active_stage_id: str | None = None     # 当前 active 的 stage_id
        self._reports: list[tuple[str, str, str]] = []
        self._verdict: str | None = None

    # ── 对外接口 ─────────────────────────────────────────

    def feed(self, chunk: Any) -> list[TradingDeskEvent]:
        """喂入一个 astream chunk，返回产生的事件（同时记录在 self.events）。"""
        produced: list[TradingDeskEvent] = []
        if not isinstance(chunk, tuple) or len(chunk) != 2:
            return produced
        mode, payload = chunk
        if mode == "messages":
            produced = self._feed_message(payload)
        elif mode == "updates":
            produced = self._feed_updates(payload)
        self.events.extend(produced)
        return produced

    def snapshot(self) -> dict[str, str]:
        """当前各节点未完结的 turn。主要供测试观察。"""
        return dict(self._current_turn)

    def text_of(self, turn_id: str) -> str:
        """某张卡片累积的完整文本。"""
        return "".join(self._turn_text.get(turn_id, []))

    def pending_reports(self) -> list[tuple[str, str, str]]:
        """取走（并清空）待抽取信号的分析师报告。"""
        out, self._reports = self._reports, []
        return out

    def verdict_text(self) -> str | None:
        """取走（并清空）待解析的裁决原始文本。"""
        text, self._verdict = self._verdict, None
        return text

    def flush_stage(self) -> list[TradingDeskEvent]:
        """收尾最后未收尾的 stage（如 risk_judge 之后不再有节点更新）。

        引擎在 astream 收尾时调用，避免「最后阶段 done 不发」。
        """
        if self._active_stage_id is None:
            return []
        ev = self._emit(EventType.STAGE_DONE, StageData(stage_id=self._active_stage_id))
        self._active_stage_id = None
        self.events.append(ev)
        return [ev]

    # ── messages 模式 ────────────────────────────────────

    def _feed_message(self, payload: Any) -> list[TradingDeskEvent]:
        if not isinstance(payload, tuple) or len(payload) != 2:
            return []
        message, metadata = payload
        node = str(metadata.get("langgraph_node") or "") if isinstance(metadata, dict) else ""
        if not stage_map.is_agent_node(node):
            return []  # tools_* / Msg Clear * 的消息不进推理流

        if not isinstance(message, AIMessageChunk):
            return []

        produced = self._ensure_turn_events(node)
        turn_id = self._current_turn[node]

        for tc in message.tool_call_chunks or []:
            name = tc.get("name")
            if name:
                produced.append(
                    self._emit(EventType.AGENT_TOOL_CALL, ToolCallData(turn_id=turn_id, tool=str(name)))
                )

        content = message.content
        if isinstance(content, str) and content:
            self._turn_text[turn_id].append(content)
            produced.append(
                self._emit(EventType.AGENT_TOKEN, TokenData(turn_id=turn_id, text=content))
            )

        return produced

    # ── updates 模式 ─────────────────────────────────────

    def _feed_updates(self, payload: Any) -> list[TradingDeskEvent]:
        if not isinstance(payload, dict):
            return []
        produced: list[TradingDeskEvent] = []

        for node, update in payload.items():
            if not stage_map.is_agent_node(node) or not isinstance(update, dict):
                continue

            stage = stage_map.stage_of(node)
            if stage is None:
                continue

            # stage 生命周期：跨 stage 切换时上一阶段先收尾，再开新阶段
            if self._active_stage_id and self._active_stage_id != stage.id:
                produced.append(
                    self._emit(EventType.STAGE_DONE, StageData(stage_id=self._active_stage_id))
                )
                self._active_stage_id = None
            if stage.id != self._active_stage_id:
                self._active_stage_id = stage.id
                produced.append(self._emit(EventType.STAGE_ACTIVE, StageData(stage_id=stage.id)))

            # 节点重入的极端情况：上一轮 turn 没收尾，先收
            if node in self._current_turn:
                produced.extend(self._close_turn(node))

            self._node_runs[node] = self._node_runs.get(node, 0) + 1

            # 本轮发言的 turn 收尾（token 已在 messages 模式里流出去）
            produced.extend(self._close_turn(node))

            meta = stage_map.debate_meta(node, self._node_runs[node])
            if meta is not None:
                turn_id = self._last_turn_of(node)
                if turn_id:
                    produced.append(
                        self._emit(
                            EventType.DEBATE_TURN,
                            DebateTurnData(
                                stage_id=stage.id,
                                debate_id=meta.debate_id,
                                side=meta.side,
                                side_label=meta.side_label,
                                polarity=meta.polarity,
                                round=self._node_runs[node],
                                turn_id=turn_id,
                            ),
                        )
                    )

            for key, (stage_id, stage_name) in _REPORT_KEYS.items():
                if key in update and update[key]:
                    self._reports.append((stage_id, stage_name, str(update[key])))

            if update.get("final_trade_decision"):
                self._verdict = str(update["final_trade_decision"])

        return produced

    # ── 内部 ─────────────────────────────────────────────

    def _ensure_turn_events(self, node: str) -> list[TradingDeskEvent]:
        """该节点本轮的卡片不存在时开一张。"""
        if node in self._current_turn:
            return []
        display = stage_map.display_of(node)
        stage = stage_map.stage_of(node)
        turn_id = f"{node}-{self._node_runs.get(node, 0) + 1}"
        self._current_turn[node] = turn_id
        self._turn_text[turn_id] = []
        return [
            self._emit(
                EventType.TURN_STARTED,
                TurnStartedData(
                    turn_id=turn_id,
                    stage_id=stage.id if stage else "",
                    name=display[0] if display else node,
                    role=display[2] if display else "",
                    avatar=display[1] if display else "",
                ),
            )
        ]

    def _close_turn(self, node: str) -> list[TradingDeskEvent]:
        """收尾该节点当前 turn。"""
        turn_id = self._current_turn.pop(node, None)
        if turn_id is None:
            return []
        self._last_turns[node] = turn_id  # 记住最近一张，debate.turn 事件要用
        return [self._emit(EventType.TURN_DONE, TurnDoneData(turn_id=turn_id))]

    def _last_turn_of(self, node: str) -> str | None:
        return self._last_turns.get(node)

    def _emit(self, type_: EventType, payload: Any) -> TradingDeskEvent:
        return TradingDeskEvent.of(self.run_id, type_, payload)
