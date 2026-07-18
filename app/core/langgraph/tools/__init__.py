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
from .fmp_data import (
    fmp_company_profile,
    fmp_financial_statement,
    fmp_key_metrics,
    fmp_quote,
)
from .ichimoku_analysis import ichimoku_analysis_tool as _ichimoku_analysis_fn
from .structure_gap import structure_gap_tool as _structure_gap_fn
from .wyckoff_analysis import wyckoff_analysis_tool as _wyckoff_analysis_fn


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


@tool
async def wyckoff_analysis(symbol: str, start_date: str, end_date: str, freq: str = "daily") -> str:
    """使用威科夫方法论（The Wyckoff Methodology）对股票进行技术分析。

    识别交易区间的支撑/阻力，判定吸筹/拉升/派发/下跌四大阶段及区间内 A–E 子阶段，
    标记威科夫事件（SC/AR/ST/Spring/SOS/UT/UTAD/SOW/LPS/LPSY 等），
    并应用三大定律（供求/因果/量价）。
    适用于美股（使用 FMP 数据）和 A 股（使用 AKShare，代码如 SH600519）。

    Args:
        symbol: 股票代码，如 'AAPL'、'NVDA' 或 'SH600519'
        start_date: 分析起始日期，格式 YYYY-MM-DD，建议至少半年数据
        end_date: 分析截止日期，格式 YYYY-MM-DD
        freq: K线周期，daily（日线）或 weekly（周线）

    Returns:
        详细的威科夫方法论分析报告文本
    """
    return await _wyckoff_analysis_fn(symbol, start_date, end_date, freq)


@tool
async def ichimoku_analysis(symbol: str, start_date: str, end_date: str, freq: str = "daily") -> str:
    """使用一目均衡表（Ichimoku Kinko Hyo，云图）对股票进行技术分析。

    计算转换线、基准线、先行带 A/B（云 Kumo）、迟行线，判断 TK 交叉、
    价格相对云的位置、云的多空色与迟行线确认，综合「三役」给出买卖信号与操作建议。
    适用于美股（使用 FMP 数据）和 A 股（使用 AKShare，代码如 SH600519）。

    Args:
        symbol: 股票代码，如 'AAPL'、'NVDA' 或 'SH600519'
        start_date: 分析起始日期，格式 YYYY-MM-DD，建议至少半年数据（云需 52+26 根）
        end_date: 分析截止日期，格式 YYYY-MM-DD
        freq: K线周期，daily（日线）或 weekly（周线）

    Returns:
        详细的一目均衡表分析报告文本
    """
    return await _ichimoku_analysis_fn(symbol, start_date, end_date, freq)


@tool
async def structure_gap_analysis(
    symbol: str,
    start_date: str,
    end_date: str,
    industry_view: str,
    freq: str = "daily",
) -> str:
    """找出一只股票【市场结构（缠论技术面）】与【产业结构（用户判断）】之间的背离（gap）。

    当用户已有自己的产业/基本面判断，想知道它和当前技术面结构是否一致、在哪里背离时使用。
    先用缠论解读当前市场结构，再与用户提供的产业观点并置，重点输出二者矛盾之处
    （技术面滞后于产业=潜在机会 / 价格领先于基本面=潜在风险），不预测涨跌、不构成投资建议。

    Args:
        symbol: 股票代码，如 'AAPL'、'NVDA' 或 'SH600519'
        start_date: 分析起始日期，格式 YYYY-MM-DD，建议至少半年数据
        end_date: 分析截止日期，格式 YYYY-MM-DD
        industry_view: 用户对该标的产业结构的判断（产业链位置、景气周期、竞争格局、需求趋势等），必填
        freq: K线周期，daily（日线）或 weekly（周线）

    Returns:
        技术面与产业面的 gap 分析报告文本
    """
    return await _structure_gap_fn(symbol, start_date, end_date, industry_view, freq)


tools: list[BaseTool] = [
    duckduckgo_search_tool,
    ask_human,
    fmp_quote,
    fmp_company_profile,
    fmp_financial_statement,
    fmp_key_metrics,
    chan_analysis,
    wyckoff_analysis,
    ichimoku_analysis,
    structure_gap_analysis,
]
