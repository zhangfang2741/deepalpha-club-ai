"""LangGraph 节点名与事件协议 stage 的映射表。

翻译器只认这里的信息；tradingagents 改节点名时集中改这一处。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.trading_desk import Polarity, StageDescriptor, StageGroup


@dataclass(frozen=True)
class DebateMeta:
    debate_id: str
    side: str
    side_label: str
    polarity: Polarity


# 节点名 -> (stage_id, 中文名, role, group)
_NODE_TO_STAGE: dict[str, tuple[str, str, str, StageGroup]] = {
    "Market Analyst": ("market_analyst", "技术面分析师", "价格行为", "analyst"),
    "Social Analyst": ("social_analyst", "社交情绪", "舆情", "analyst"),
    "News Analyst": ("news_analyst", "消息与新闻", "资讯流", "analyst"),
    "Fundamentals Analyst": ("fundamentals_analyst", "基本面分析师", "价值", "analyst"),
    "Situation Summariser": ("situation_summary", "情境摘要", "汇总", "system"),
    "Bull Researcher": ("research_debate", "研究员辩论", "多空对辩", "debate"),
    "Bear Researcher": ("research_debate", "研究员辩论", "多空对辩", "debate"),
    "Research Manager": ("research_manager", "研究主管", "裁定", "manager"),
    "Trader": ("trader", "交易员", "综合", "trader"),
    "Aggressive Analyst": ("risk_debate", "风控委员会", "三方评议", "debate"),
    "Conservative Analyst": ("risk_debate", "风控委员会", "三方评议", "debate"),
    "Neutral Analyst": ("risk_debate", "风控委员会", "三方评议", "debate"),
    "Risk Judge": ("risk_judge", "风控裁决", "最终决策", "manager"),
}

# 辩论参与方的门派信息。风控三方：激进=偏多、保守=偏空、中立=中性
_DEBATE_META: dict[str, DebateMeta] = {
    "Bull Researcher": DebateMeta("research", "bull", "多头研究员", "bull"),
    "Bear Researcher": DebateMeta("research", "bear", "空头研究员", "bear"),
    "Aggressive Analyst": DebateMeta("risk", "aggressive", "激进派", "bull"),
    "Conservative Analyst": DebateMeta("risk", "conservative", "保守派", "bear"),
    "Neutral Analyst": DebateMeta("risk", "neutral", "中立派", "neutral"),
}

# 顺序对应 tradingagents 的真实串行拓扑（计划三前置侦察实测：
# 风控辩论顺序是 Aggressive → Conservative → Neutral）
AGENT_NODES = tuple(_NODE_TO_STAGE)

# 发言人显示信息：节点名 -> (显示名, 头像缩写, role)
_NODE_DISPLAY: dict[str, tuple[str, str, str]] = {
    "Market Analyst": ("技术面分析师", "TA", "价格行为"),
    "Social Analyst": ("社交情绪", "SA", "舆情"),
    "News Analyst": ("消息与新闻", "NA", "资讯流"),
    "Fundamentals Analyst": ("基本面分析师", "FA", "价值"),
    "Situation Summariser": ("情境摘要", "SS", "汇总"),
    "Bull Researcher": ("多头研究员", "BR", "研究员"),
    "Bear Researcher": ("空头研究员", "BE", "研究员"),
    "Research Manager": ("研究主管", "RM", "裁定"),
    "Trader": ("交易员", "TR", "综合"),
    "Aggressive Analyst": ("激进派", "AG", "风控"),
    "Conservative Analyst": ("保守派", "CO", "风控"),
    "Neutral Analyst": ("中立派", "NE", "风控"),
    "Risk Judge": ("风控裁决", "RJ", "最终决策"),
}

# tradingagents 在 debate_state 里给发言加的前缀，渲染前剥掉
_SPEAKER_PREFIXES = (
    "Bull Analyst: ",
    "Bear Analyst: ",
    "Aggressive Analyst: ",
    "Conservative Analyst: ",
    "Neutral Analyst: ",
    "Judge: ",
)


def is_agent_node(node: str) -> bool:
    """是否为语义节点。tools_* 与 Msg Clear * 管道节点返回 False。"""
    return node in _NODE_TO_STAGE


def stage_of(node: str) -> StageDescriptor | None:
    """取节点对应的 stage 描述符；管道节点与未知节点返回 None。"""
    entry = _NODE_TO_STAGE.get(node)
    if entry is None:
        return None
    stage_id, name, role, group = entry
    return StageDescriptor(id=stage_id, name=name, role=role, group=group)


def display_of(node: str) -> tuple[str, str, str] | None:
    """取发言人显示信息 (显示名, 头像缩写, role)。"""
    return _NODE_DISPLAY.get(node)


def debate_meta(node: str, round_no: int) -> DebateMeta | None:
    """辩论节点取门派信息；非辩论节点返回 None。

    round_no 只是签名占位（由调用方填进 DebateTurnData），映射表本身不存轮次。
    """
    return _DEBATE_META.get(node)


def strip_speaker_prefix(text: str) -> str:
    """剥掉 debate_state 发言自带的前缀（如 "Bull Analyst: "）。"""
    for prefix in _SPEAKER_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text
