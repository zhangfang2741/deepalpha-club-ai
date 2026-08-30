"""stage_map：LangGraph 节点名与事件协议 stage 的映射。"""

from __future__ import annotations

from app.services.trading_desk.engines import stage_map


def test_agent_nodes_cover_all_semantic_nodes() -> None:
    """interrupt_before 要挂的 13 个语义节点，一个不能少。"""
    assert set(stage_map.AGENT_NODES) == {
        "Market Analyst", "Social Analyst", "News Analyst", "Fundamentals Analyst",
        "Situation Summariser", "Bull Researcher", "Bear Researcher",
        "Research Manager", "Trader",
        "Aggressive Analyst", "Conservative Analyst", "Neutral Analyst",
        "Risk Judge",
    }


def test_agent_nodes_follow_real_topology_order() -> None:
    """顺序对应 tradingagents 真实串行拓扑（风控辩论是 A→C→N）。"""
    assert list(stage_map.AGENT_NODES)[:4] == [
        "Market Analyst", "Social Analyst", "News Analyst", "Fundamentals Analyst",
    ]
    assert list(stage_map.AGENT_NODES)[9:] == [
        "Aggressive Analyst", "Conservative Analyst", "Neutral Analyst", "Risk Judge",
    ]


def test_pipeline_nodes_are_excluded() -> None:
    """tools_* 与 Msg Clear * 是管道节点，不产生用户可见事件。"""
    assert not stage_map.is_agent_node("tools_market")
    assert not stage_map.is_agent_node("Msg Clear Market")
    assert stage_map.is_agent_node("Bull Researcher")


def test_stage_of_covers_every_agent_node() -> None:
    for node in stage_map.AGENT_NODES:
        assert stage_map.stage_of(node) is not None, f"{node} 缺 stage 映射"


def test_stage_of_returns_none_for_unknown() -> None:
    assert stage_map.stage_of("tools_market") is None
    assert stage_map.stage_of("whatever") is None


def test_debate_meta_for_researchers() -> None:
    bull = stage_map.debate_meta("Bull Researcher", round_no=2)
    assert bull is not None
    assert bull.polarity == "bull"
    assert bull.debate_id == "research"

    aggr = stage_map.debate_meta("Aggressive Analyst", round_no=1)
    assert aggr is not None
    assert aggr.debate_id == "risk"
    assert aggr.polarity == "bull"          # 激进派偏多
    assert stage_map.debate_meta("Conservative Analyst", 1).polarity == "bear"
    assert stage_map.debate_meta("Neutral Analyst", 1).polarity == "neutral"


def test_debate_meta_none_for_non_debate_nodes() -> None:
    assert stage_map.debate_meta("Market Analyst", 1) is None


def test_display_of_every_agent_node() -> None:
    for node in stage_map.AGENT_NODES:
        display = stage_map.display_of(node)
        assert display is not None, f"{node} 缺显示信息"
        name, avatar, role = display
        assert name and avatar, f"{node} 显示信息不完整"


def test_strip_speaker_prefix() -> None:
    assert stage_map.strip_speaker_prefix("Bull Analyst: 论点") == "论点"
    assert stage_map.strip_speaker_prefix("Conservative Analyst: 论点") == "论点"
    assert stage_map.strip_speaker_prefix("没有前缀") == "没有前缀"
