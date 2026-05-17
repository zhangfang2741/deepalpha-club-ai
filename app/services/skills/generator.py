"""流式代码生成：SSE 流式输出 LLM 生成的因子代码。"""
from __future__ import annotations

import json
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.logging import logger
from app.services.llm.registry import llm_registry

_SYSTEM_PROMPT = """你是一位量化因子工程师。用户描述一个量化因子，你输出可执行的 Python 函数。

可用数据（**重要：每类数据的性质不同，请仔细阅读**）：
1. prices：按日期升序的 K 线 list，每条 dict 含 date/open/high/low/close/volume
   示例：[{"date": "2024-01-01", "open": 119, "high": 122, "low": 118, "close": 120.5, "volume": 1000000}]
   这是时间序列，可以计算任何基于价格/成交量的时序因子（均线、MACD、RSI、布林带等）
2. financials 是 dict，包含以下时间序列数据：
   - income_statement：季度利润表，含 revenue/netIncome/grossProfit/operatingIncome/eps/epsDiluted
   - balance_sheet：季度资产负债表，含 totalAssets/totalLiabilities/totalEquity/cash/debt
   - cash_flow：季度现金流量表，含 operatingCashFlow/freeCashFlow/capex/dividendsPaid
   - key_metrics：季度关键指标，含 pe/pb/ps/roe/roa/ros/gpm/npm/de/currentRatio/quickRatio/dividendYield
   - analyst_estimates：分析师预测（**时间序列**），含 epsAvg/epsHigh/epsLow/revenueAvg/revenueHigh/revenueLow/numberAnalysts
   - earnings：盈利日程（含 epsActual/epsSurprise），可做"超预期"因子
   - dividends：股息历史（**时间序列**），含 dividendAmount/yield
   - dcf：DCF 估值历史，含 dcf/sharePrice
   - profile：**当前静态快照**，含 name/industry/sector/marketCap/price/employees
   - employee_count：**年度时间序列**，含 date/employeeCount，可用于计算"员工增长超过20%"等因子
     **重要：employee_count 是时间序列，可以用 pandas 计算同比增长率**
3. news：list，每条含 date/title/text/sentiment/sentimentScore/source
4. analyst_estimates / dcf / dividends / earnings 也作为顶层变量直接可用

**代码生成原则**：
1. 定义 compute(prices, symbol) -> list[dict]
2. 先检查数据是否可用再用，不要假数据存在。例如：
   - 如果你想用 analyst_estimates，先检查 `analyst_estimates and len(analyst_estimates) > 0`
   - 如果数据为空或 None，返回空 list [] 或尝试用 prices 计算替代指标
3. 返回格式：list[{"time": "2024-01-01", "value": 0.05}]，time 复用 prices 中的 date 字符串
4. 沙箱已注入 np/pd/math，直接使用，禁止写 import 语句
5. 禁止：os / subprocess / socket / requests / __import__ / eval / exec / open
6. 代码简洁，注释用中文；NaN/Inf 必须过滤后再返回
7. 输出纯净 Markdown：1-2 句中文说明 + 一个 ```python 代码块，禁止 SSE/JSON 包装

**数据不可用时的策略**：
- 如果用户要求的因子依赖不可用的数据，优先尝试用 prices 计算近似的替代因子
- 例如：用户要求"员工增长"但 employees 不是时间序列 → 用公司规模（marketCap）或收入增长作为替代
- 如果完全无法计算，返回空 list []（不是 None，不是错误）

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
