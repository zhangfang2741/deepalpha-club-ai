"""流翻译器：LangGraph chunk -> 事件协议。纯函数测试，不跑图。"""

from __future__ import annotations

from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage

from app.schemas.trading_desk import EventType
from app.services.trading_desk.engines import stream_translator as st


def _token_chunk(node: str, text: str) -> tuple[str, tuple]:
    msg = AIMessageChunk(content=text)
    return ("messages", (msg, {"langgraph_node": node}))


def _tool_chunk(node: str, tool: str) -> tuple[str, tuple]:
    msg = AIMessageChunk(
        content="",
        tool_call_chunks=[
            {"name": tool, "args": '{"ticker": "NVDA"}', "id": "t1", "index": 0, "type": "tool_call_chunk"}
        ],
    )
    return ("messages", (msg, {"langgraph_node": node}))


def test_first_token_opens_turn_then_accumulates() -> None:
    tr = st.StreamTranslator(run_id="r1")
    opened = tr.feed(_token_chunk("Market Analyst", "回调后"))
    assert [e.type for e in opened] == [EventType.TURN_STARTED, EventType.AGENT_TOKEN]

    tr.feed(_token_chunk("Market Analyst", "站稳"))

    turn_id = tr.snapshot()["Market Analyst"]
    assert tr.text_of(turn_id) == "回调后站稳"


def test_tool_and_continue_messages_are_filtered() -> None:
    tr = st.StreamTranslator(run_id="r1")
    tool_result = ("messages", (ToolMessage(content="工具结果", tool_call_id="t1"), {"langgraph_node": "tools_market"}))
    continue_msg = ("messages", (HumanMessage(content="Continue"), {"langgraph_node": "Msg Clear Market"}))

    assert tr.feed(tool_result) == []
    assert tr.feed(continue_msg) == []


def test_tool_call_chunk_becomes_agent_tool_call() -> None:
    tr = st.StreamTranslator(run_id="r1")
    tr.feed(_token_chunk("Market Analyst", ""))
    events = tr.feed(_tool_chunk("Market Analyst", "get_stock_data"))

    types = [e.type for e in events]
    assert EventType.AGENT_TOOL_CALL in types
    tc = next(e for e in events if e.type is EventType.AGENT_TOOL_CALL)
    assert tc.data["tool"] == "get_stock_data"


def test_node_update_closes_turn_and_opens_stage() -> None:
    """单个节点 update：开 active、收 turn；但 stage.done 只在切换或 flush 时发。"""
    tr = st.StreamTranslator(run_id="r1")
    tr.feed(_token_chunk("Market Analyst", "文本"))
    events = tr.feed(("updates", {"Market Analyst": {"messages": None, "market_report": "报告"}}))

    types = [e.type for e in events]
    assert EventType.STAGE_ACTIVE in types
    assert EventType.TURN_DONE in types
    assert EventType.STAGE_DONE not in types  # 单节点不会自动 done


def test_flush_stage_emits_done_for_last_stage() -> None:
    """flush_stage 收尾未关闭的 stage（防止最末阶段漏 done）。"""
    tr = st.StreamTranslator(run_id="r1")
    tr.feed(_token_chunk("Risk Judge", "裁决"))
    tr.feed(("updates", {"Risk Judge": {"final_trade_decision": "BUY"}}))

    done_events = tr.flush_stage()
    assert [e.type for e in done_events] == [EventType.STAGE_DONE]
    assert done_events[0].data["stage_id"] == "risk_judge"
    assert tr.flush_stage() == []  # 多次调用幂等


def test_stage_done_fires_on_transition() -> None:
    """阶段切换：上一个 stage.done 在新 stage.active 之前发出。"""
    tr = st.StreamTranslator(run_id="r1")
    tr.feed(("updates", {"Market Analyst": {"market_report": "r1"}}))
    events = tr.feed(("updates", {"Social Analyst": {"sentiment_report": "r2"}}))

    stage_events = [e for e in events if e.type in (EventType.STAGE_DONE, EventType.STAGE_ACTIVE)]
    assert [e.type for e in stage_events] == [EventType.STAGE_DONE, EventType.STAGE_ACTIVE]
    assert stage_events[0].data["stage_id"] == "market_analyst"
    assert stage_events[1].data["stage_id"] == "social_analyst"


def test_report_completion_marks_extractable_signal() -> None:
    tr = st.StreamTranslator(run_id="r1")
    tr.feed(_token_chunk("News Analyst", "消息面"))
    tr.feed(("updates", {"News Analyst": {"news_report": "报告"}}))

    assert tr.pending_reports() == [("news_analyst", "消息与新闻", "报告")]
    assert tr.pending_reports() == []  # 取走即清


def test_debate_turn_events_carry_polarity_and_round() -> None:
    tr = st.StreamTranslator(run_id="r1")
    tr.feed(_token_chunk("Bull Researcher", "论点"))
    events = tr.feed(("updates", {"Bull Researcher": {"investment_debate_state": object()}}))

    debate = [e for e in events if e.type is EventType.DEBATE_TURN]
    assert debate[0].data["polarity"] == "bull"
    assert debate[0].data["round"] == 1

    # 第二轮再执行时轮次递增
    tr.feed(_token_chunk("Bull Researcher", "第二轮"))
    events = tr.feed(("updates", {"Bull Researcher": {"investment_debate_state": object()}}))
    debate = [e for e in events if e.type is EventType.DEBATE_TURN]
    assert debate[0].data["round"] == 2


def test_risk_debate_sides_map_to_polarities() -> None:
    tr = st.StreamTranslator(run_id="r1")
    for node, expect in (("Aggressive Analyst", "bull"), ("Conservative Analyst", "bear"), ("Neutral Analyst", "neutral")):
        tr.feed(_token_chunk(node, "发言"))
        events = tr.feed(("updates", {node: {"risk_debate_state": object()}}))
        debate = [e for e in events if e.type is EventType.DEBATE_TURN]
        assert debate[0].data["polarity"] == expect, node
        assert debate[0].data["debate_id"] == "risk"


def test_final_trade_decision_flags_verdict_ready() -> None:
    tr = st.StreamTranslator(run_id="r1")
    tr.feed(("updates", {"Risk Judge": {"final_trade_decision": "BUY 一切"}}))

    assert tr.verdict_text() == "BUY 一切"
    assert tr.verdict_text() is None  # 取走即清


def test_second_execution_of_same_node_starts_fresh_turn() -> None:
    """同一节点第二次执行（如辩论第二轮）不叠加上一轮文本。"""
    tr = st.StreamTranslator(run_id="r1")
    tr.feed(_token_chunk("Bear Researcher", "第一轮"))
    tr.feed(("updates", {"Bear Researcher": {"investment_debate_state": object()}}))
    tr.feed(_token_chunk("Bear Researcher", "第二轮"))
    tr.feed(("updates", {"Bear Researcher": {"investment_debate_state": object()}}))

    debates = [e for e in tr.events if e.type is EventType.DEBATE_TURN]
    assert [d.data["round"] for d in debates] == [1, 2]

    turns = [e for e in tr.events if e.type is EventType.TURN_STARTED]
    assert len(turns) == 2  # 两轮各自一张卡片


def test_pipeline_node_updates_are_ignored() -> None:
    tr = st.StreamTranslator(run_id="r1")
    assert tr.feed(("updates", {"tools_market": {"messages": None}})) == []
    assert tr.feed(("updates", {"Msg Clear Market": {"messages": None}})) == []


def test_unknown_chunk_shapes_are_ignored() -> None:
    tr = st.StreamTranslator(run_id="r1")
    assert tr.feed(("whatever", "payload")) == []
    assert tr.feed(None) == []
    assert tr.feed(("messages", "bad payload")) == []
