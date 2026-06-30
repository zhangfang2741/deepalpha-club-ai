"""LangGraph tools for enhanced language model capabilities.

This package contains custom tools that can be used with LangGraph to extend
the capabilities of language models. Currently includes tools for web search
and other external integrations.
"""

from langchain_core.tools import tool
from langchain_core.tools.base import BaseTool

from .ask_human import ask_human
from .chan_analysis import chan_analysis_tool as _chan_analysis_fn
from .duckduckgo_search import duckduckgo_search_tool


@tool
async def chan_analysis(symbol: str, start_date: str, end_date: str, freq: str = "daily") -> str:
    """使用缠论（缠中说禅理论）对股票进行技术分析。

    识别分型、笔、线段、中枢，判断背驰，生成三类买卖点（一买/二买/三买及卖点）。
    适用于美股（使用 FMP 数据）和 A 股（使用 AKShare，代码如 SH600519）。

    Args:
        symbol: 股票代码，如 'AAPL'、'NVDA' 或 'SH600519'
        start_date: 分析起始日期，格式 YYYY-MM-DD，建议至少半年数据
        end_date: 分析截止日期，格式 YYYY-MM-DD
        freq: K线周期，daily（日线）或 weekly（周线）

    Returns:
        详细的缠论分析报告文本
    """
    return await _chan_analysis_fn(symbol, start_date, end_date, freq)


tools: list[BaseTool] = [duckduckgo_search_tool, ask_human, chan_analysis]
