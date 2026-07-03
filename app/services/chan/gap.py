"""市场结构 × 产业结构的 GAP 分析。

把缠论产出的【市场结构】（技术面）与用户提供的【产业结构】（主观基本面判断）
并置，交给 LLM 找出二者之间的背离（gap）。核心立场：价值在“背离”而非“印证”，
且诚实对待技术面右侧的未确认结构与产业判断的主观性——不预测涨跌，只指出矛盾。
"""
from __future__ import annotations

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.core.logging import logger
from app.services.chan.analyzer import ChanAnalysisResult
from app.services.llm.service import llm_service


class GapItem(BaseModel):
    """一处技术面与产业面的背离。"""

    dimension: str = Field(description="背离的维度，如“趋势方向”“景气周期”“估值/情绪”")
    market_says: str = Field(description="技术面（缠论）在该维度上传达的信息")
    industry_says: str = Field(description="产业面（用户判断）在该维度上传达的信息")
    direction: Literal["price_lags_industry", "price_ahead_of_fundamentals", "unclear"] = Field(
        description=(
            "背离方向：price_lags_industry=技术面弱/滞后但产业向上（市场或尚未反映，潜在机会）；"
            "price_ahead_of_fundamentals=技术面强/领先但产业已透支或转弱（价格跑在基本面前，潜在风险）；"
            "unclear=信息不足以判断"
        )
    )
    interpretation: str = Field(description="该背离可能意味着什么（不下买卖结论）")


class GapAnalysis(BaseModel):
    """市场结构 × 产业结构的 gap 分析结果。"""

    aligned: list[str] = Field(
        default_factory=list,
        description="技术面与产业面一致之处（多已被市场定价，简述即可）",
    )
    gaps: list[GapItem] = Field(
        default_factory=list,
        description="技术面与产业面的背离之处（重点）",
    )
    key_question: str = Field(
        default="",
        description="综合 gap 后，最值得进一步研究的一个问题",
    )
    caveats: list[str] = Field(
        default_factory=list,
        description="诚实边界：技术面右侧未确认、产业判断为主观输入等",
    )


_SYSTEM_PROMPT = """你是一位同时精通技术分析（缠论）与产业基本面的研究员。
用户会给你两样东西：
1. 一只股票【当前市场结构】的技术面解读（缠论：分型/笔/线段/中枢/背驰/买卖点，其中带“未确认”标注的是最右侧尚未走完、随时可能变化的结构）。
2. 用户自己对该公司/行业【产业结构】的判断（主观输入，可能不完整）。

你的任务不是预测涨跌，而是找出这两者之间的 GAP（背离）。严格遵守：

核心原则——价值在“背离”，不在“印证”：
- 技术面与产业面说同一件事 → 多已被市场定价，放进 aligned 简要带过即可。
- 二者矛盾 → 这才是重点，放进 gaps，逐条给出维度、双方各自在说什么、方向与可能含义。
- 背离方向只分三类：price_lags_industry（技术弱/滞后但产业向上，市场或未反映，潜在机会）、
  price_ahead_of_fundamentals（技术强/领先但产业透支或转弱，价格跑在基本面前，潜在风险）、unclear。

诚实要求（非常重要）：
- 技术结构中标注“未确认”的部分说明结论随时可能变，凡依赖它得出的 gap，要在 interpretation 里点明其确定性较低。
- 产业结构是用户的主观判断，不要凭空编造用户没有提供的产业事实；信息不足就说信息不足。
- 全程不构成投资建议，不给出具体买卖点位或仓位。

输出：中文，简洁克制，宁缺毋滥；没有真正的背离时 gaps 可以为空并如实说明。"""


def build_market_digest(result: ChanAnalysisResult) -> str:
    """把缠论分析结果压缩成给 LLM 的【市场结构】摘要文本（确定性部分，纯函数）。"""
    lines: list[str] = [f"标的：{result.symbol}"]

    if result.current_trend:
        lines.append(f"当前趋势：{result.current_trend}")

    if result.segments:
        seg = result.segments[-1]
        tag = "" if seg.confirmed else "（未确认）"
        lines.append(f"最近线段方向：{'向上' if seg.direction == 'up' else '向下'}{tag}（大级别）")

    if result.strokes:
        s = result.strokes[-1]
        tag = "" if s.confirmed else "（未确认，端点可能延伸/反转）"
        lines.append(f"最后一笔：{'上升' if s.direction == 'up' else '下降'}{tag}")

    last_price = result.merged_candles[-1].close if result.merged_candles else None
    if result.stroke_pivots:
        p = result.stroke_pivots[-1]
        tag = "" if p.confirmed else "（可能仍在延伸）"
        pos = ""
        if last_price is not None:
            if last_price > p.zg:
                pos = "，当前价站上中枢上沿（多头占优）"
            elif last_price < p.zd:
                pos = "，当前价跌破中枢下沿（空头占优）"
            else:
                pos = "，当前价仍在中枢内（多空交战）"
        lines.append(f"最近笔级中枢：{p.zd:.2f}–{p.zg:.2f}{tag}{pos}")

    diverged = [(st, dv) for st, dv in zip(result.strokes, result.divergences, strict=False) if dv.is_diverged]
    if diverged:
        st, dv = diverged[-1]
        kind = "顶背驰" if st.direction == "up" else "底背驰"
        lines.append(f"最近背驰：{kind}（{dv.strength}），动能衰竭迹象")

    if result.signals:
        recent = result.signals[-3:]
        sig_desc = "、".join(
            f"{s.label}{'（未确认）' if not s.confirmed else ''}" for s in recent
        )
        lines.append(f"最近买卖点：{sig_desc}")

    if last_price is not None:
        lines.append(f"最新价：{last_price:.2f}")

    if result.pending_notes:
        lines.append("【最右侧未确认结构】" + "；".join(result.pending_notes))

    return "\n".join(lines)


async def analyze_structure_gap(
    result: ChanAnalysisResult,
    industry_view: str,
) -> GapAnalysis:
    """并置市场结构与产业结构，产出 gap 分析。

    result: 缠论分析结果（市场结构 / 技术面）
    industry_view: 用户对该标的产业结构的判断（主观基本面输入）
    """
    market_digest = build_market_digest(result)

    user_content = (
        "## 市场结构（技术面 · 缠论）\n"
        f"{market_digest}\n\n"
        "## 产业结构（用户的主观判断）\n"
        f"{industry_view.strip()}\n\n"
        "请依据以上两者，找出并解释它们之间的 gap。"
    )

    logger.info("structure_gap_start", symbol=result.symbol, industry_view_len=len(industry_view))

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_content)]
    analysis = await llm_service.call(messages, response_format=GapAnalysis, temperature=0.4)

    logger.info(
        "structure_gap_complete",
        symbol=result.symbol,
        gaps=len(analysis.gaps),
        aligned=len(analysis.aligned),
    )
    return analysis
