"""流式代码生成：SSE 流式输出 LLM 生成的因子代码。"""
from __future__ import annotations

import json
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.logging import logger
from app.services.llm.registry import llm_registry

_SYSTEM_PROMPT = """你是一位量化因子工程师。用户描述一个量化因子，你输出可执行的 Python 函数。

可用数据：
1. prices：按日期升序的 K 线 list，每条 dict 含 date/open/high/low/close/volume
   示例：[{"date": "2024-01-01", "open": 119, "high": 122, "low": 118, "close": 120.5, "volume": 1000000}]
   注意：prices 已按时间升序，不需要 sort_values，字段名全为小写
2. financials：dict，含以下 key（部分数据可能为空 list/dict）：
   - income_statement：季度利润表，含 revenue/netIncome/grossProfit/operatingIncome/eps/epsDiluted
   - balance_sheet：季度资产负债表，含 totalAssets/totalLiabilities/totalEquity/cash/debt
   - cash_flow：季度现金流量表，含 operatingCashFlow/freeCashFlow/capex/dividendsPaid
   - key_metrics：季度关键指标，含 pe/pb/ps/roe/roa/ros/gpm/npm/de/currentRatio/quickRatio/dividendYield
   - analyst_estimates：分析师预测，含 epsAvg/epsHigh/epsLow/revenueAvg/revenueHigh/revenueLow/numberAnalysts
   - earnings：盈利日程，含 epsActual/epsSurprise/revenueActual/revenueEstimate
   - dividends：股息历史，含 dividendAmount/yield
   - dcf：DCF 估值历史，含 dcf/sharePrice
   - profile：公司概况，含 name/industry/sector/marketCap/price
3. news：list，每条含 date/title/text/sentiment/sentimentScore/source
   sentimentScore 范围 [-1, 1]，正值代表乐观
4. analyst_estimates / dcf / dividends / earnings 也作为顶层变量直接可用

要求：
1. 定义 compute(prices, symbol) -> list[dict]
2. 返回格式：list[{"time": "2024-01-01", "value": 0.05}]，time 复用 prices 中的 date 字符串
3. 沙箱已注入 np/pd/math，直接使用，禁止写 import 语句
4. 禁止：os / subprocess / socket / requests / __import__ / eval / exec / open
5. 代码简洁，注释用中文；NaN/Inf 必须过滤后再返回
6. 输出纯净 Markdown：1-2 句中文说明 + 一个 ```python 代码块，禁止 SSE/JSON 包装
"""


async def generate_skill_stream(messages: list) -> AsyncGenerator[str, None]:
    """SSE 流式生成 skill 代码，yield 每个 SSE data 帧。"""
    llm = llm_registry.get_default()

    chain_msgs = [SystemMessage(content=_SYSTEM_PROMPT)]
    for m in messages:
        role = getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else "user")
        content = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else "")
        if role == "user":
            chain_msgs.append(HumanMessage(content=content))
        else:
            chain_msgs.append(AIMessage(content=content))

    logger.info("skill_generate_start", turns=len(messages))
    async for chunk in llm.astream(chain_msgs):
        text = chunk.content if isinstance(chunk.content, str) else ""
        if text:
            yield f"data: {json.dumps({'content': text, 'done': False})}\n\n"

    yield f"data: {json.dumps({'content': '', 'done': True})}\n\n"
