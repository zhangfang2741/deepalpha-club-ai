"""市场结构 × 产业结构 GAP 分析工具：让 AI Agent 找出技术面与产业面的背离。"""
from __future__ import annotations

from app.cache.client import current_redis
from app.core.logging import logger
from app.services.chan.analyzer import ChanAnalyzer
from app.services.chan.gap import GapAnalysis, analyze_structure_gap
from app.services.skills.kline import fetch_kline

_analyzer = ChanAnalyzer()

_DIRECTION_LABEL = {
    "price_lags_industry": "技术面滞后于产业（市场或未反映，潜在机会）",
    "price_ahead_of_fundamentals": "价格领先于基本面（或已透支，潜在风险）",
    "unclear": "方向不明（信息不足）",
}


def _format_report(symbol: str, analysis: GapAnalysis) -> str:
    lines = [f"## {symbol} 市场结构 × 产业结构 GAP 分析", ""]

    if analysis.gaps:
        lines.append("### 🔍 背离（重点）")
        for i, g in enumerate(analysis.gaps, 1):
            lines.append(f"**{i}. {g.dimension}** —— {_DIRECTION_LABEL.get(g.direction, g.direction)}")
            lines.append(f"- 技术面：{g.market_says}")
            lines.append(f"- 产业面：{g.industry_says}")
            lines.append(f"- 可能含义：{g.interpretation}")
            lines.append("")
    else:
        lines.append("### 🔍 背离")
        lines.append("未发现明显背离——技术面与产业面大体一致（多已被市场定价）。")
        lines.append("")

    if analysis.aligned:
        lines.append("### ✅ 一致处（多已定价，略过）")
        for a in analysis.aligned:
            lines.append(f"- {a}")
        lines.append("")

    if analysis.key_question:
        lines.append("### ❓ 最值得研究的问题")
        lines.append(analysis.key_question)
        lines.append("")

    if analysis.caveats:
        lines.append("> " + "；".join(analysis.caveats))

    return "\n".join(lines)


async def structure_gap_tool(
    symbol: str,
    start_date: str,
    end_date: str,
    industry_view: str,
    freq: str = "daily",
) -> str:
    """对一只股票，找出【市场结构（缠论技术面）】与【产业结构（用户判断）】之间的背离。

    先用缠论分析当前市场结构，再把它与用户提供的产业观点并置，输出二者的 gap。
    """
    if not industry_view or not industry_view.strip():
        return (
            "需要你先提供对该标的的产业结构判断（如：所处产业链位置、景气周期、"
            "竞争格局、需求趋势等），我才能找出它和技术面之间的 gap。"
        )

    logger.info("structure_gap_tool_called", symbol=symbol, start=start_date, end=end_date)

    try:
        bars = await fetch_kline(
            user_id=None,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            freq=freq,
            redis=current_redis(),
        )
    except ValueError as e:
        return f"获取 {symbol} 数据失败：{e}"

    if not bars:
        return f"未能获取 {symbol} 的K线数据，请检查股票代码和日期范围。"

    result = _analyzer.analyze(symbol, bars)

    try:
        analysis = await analyze_structure_gap(result, industry_view)
    except Exception as e:
        logger.exception("structure_gap_failed", symbol=symbol, error=str(e))
        return f"生成 {symbol} 的结构 gap 分析失败，请稍后再试。"

    return _format_report(symbol, analysis)
