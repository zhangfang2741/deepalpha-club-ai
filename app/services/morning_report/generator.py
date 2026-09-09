"""两阶段晨报生成：

阶段一 recon：LLM 绑工具（搜索+行情）自由查证，输出调研笔记（自由文本）。
  - 不用 llm_service.call 的默认路径（它的 self._llm 是 chatbot 的 agent 模型，工具集不对，
    且 bind_tools 会把工具永久绑定到全局单例上，污染聊天 Agent）；
    从 registry 直接取一个模型实例 bind_tools（bind_tools 返回新的 RunnableBinding，
    不会修改 registry 里的共享单例），手写 tool-calling 循环。
阶段二 write：调研笔记 + 写作 prompt → llm_service.call(response_format=schema)。
  - with_structured_output 与 bind_tools 走同一 function-calling 机制会冲突，
    两阶段拆开天然规避。
"""

import asyncio
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig, RunnableLambda
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.langgraph.tools.duckduckgo_search import duckduckgo_search_tool
from app.core.langgraph.tools.fmp_data import (
    fmp_company_profile,
    fmp_financial_statement,
    fmp_quote,
)
from app.core.logging import logger
from app.core.observability import langfuse_callback_handler
from app.services.llm.registry import llm_registry
from app.services.llm.service import llm_service
from app.services.morning_report.data_tools import AKSHARE_TOOLS
from app.services.morning_report.prompts import render_prompt
from app.services.morning_report.schema import MorningReportContent

MAX_TOOL_ROUNDS = 6
WRITE_ATTEMPTS = 2
TOOL_RESULT_LIMIT = 4000


def build_tools(market: str) -> list[Any]:
    """按市场选择工具集：us 用 FMP+搜索；cn/hk 用 akshare+搜索。"""
    if market == "us":
        return [duckduckgo_search_tool, fmp_quote, fmp_company_profile, fmp_financial_statement]
    return [duckduckgo_search_tool, *AKSHARE_TOOLS]


def _recon_llm(market: str) -> Any:
    """从 registry 取干净的默认模型实例 + 绑市场工具（测试 monkeypatch 点）。

    注意：不能用 llm_service.bind_tools()——它会把工具绑定写回全局单例
    self._llm，污染聊天 Agent 的默认模型。这里直接用 registry.get_default()
    拿到的 BaseChatModel 调用 .bind_tools()，返回值是全新的 RunnableBinding，
    不影响 registry 里的共享实例。
    """
    return llm_registry.get_default().bind_tools(build_tools(market))


async def recon(market: str, trade_date: str) -> str:
    """阶段一：侦察。返回调研笔记文本。"""
    tools = build_tools(market)
    llm = _recon_llm(market)
    messages: list[Any] = [
        SystemMessage(content=render_prompt("recon", market, trade_date)),
        HumanMessage(content="开始侦察，完成后直接输出调研笔记。"),
    ]
    for _round in range(MAX_TOOL_ROUNDS):
        resp = await llm.ainvoke(messages)
        messages.append(resp)
        calls = getattr(resp, "tool_calls", None) or []
        if not calls:
            return str(resp.content)
        for tc in calls:
            messages.append(await _run_tool(tc, tools))
    logger.warning("morning_report_recon_round_limit", market=market)
    messages.append(HumanMessage(content="工具查询额度已用完。请综合以上全部工具结果，输出完整调研笔记，不再调用工具。"))
    response = await llm_registry.get_default().ainvoke(messages)
    if not response.content or getattr(response, "tool_calls", None):
        raise ValueError("侦察阶段未能生成完整调研笔记")
    return str(response.content)


async def _run_tool(tool_call: dict, tools: list[Any]) -> ToolMessage:
    tool = next((t for t in tools if t.name == tool_call["name"]), None)
    if tool is None:
        return ToolMessage(content=f"未知工具: {tool_call['name']}", tool_call_id=tool_call["id"])
    try:
        result = await tool.ainvoke(tool_call["args"])
    except Exception as exc:  # noqa: BLE001 —— 工具失败转文字反馈给模型
        result = f"工具执行失败: {exc}"
    return ToolMessage(content=str(result)[:TOOL_RESULT_LIMIT], tool_call_id=tool_call["id"])


async def write(notes: str, market: str, trade_date: str) -> MorningReportContent:
    """阶段二：写作。校验失败带错误重试（repair loop）。"""
    prompt = render_prompt("write", market, trade_date)
    error_hint = ""
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(WRITE_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    ):
        with attempt:
            try:
                return await llm_service.call(
                    messages=[
                        SystemMessage(content=prompt),
                        HumanMessage(content=f"调研笔记：\n{notes}\n\n请输出晨报 JSON。{error_hint}"),
                    ],
                    response_format=MorningReportContent,
                    timeout=300,
                )
            except Exception as exc:
                error_hint = f"\n\n上一次输出不合格：{exc}。请严格修正后重新输出。"
                logger.exception(
                    "morning_report_write_retry", market=market,
                    attempt=attempt.retry_state.attempt_number,
                )
                raise
    raise RuntimeError("晨报写作未返回内容")


async def generate_report(market: str, trade_date: str) -> tuple[MorningReportContent, dict]:
    """入口：返回 (内容, 元信息)。元信息含耗时/重试次数，供任务层落库。"""
    started = time.monotonic()
    config: RunnableConfig = {
        "callbacks": [langfuse_callback_handler] if settings.LANGFUSE_TRACING_ENABLED else [],
        "metadata": {"market": market, "trade_date": trade_date},
        "run_name": "morning_report",
    }

    async def generate(_: str) -> MorningReportContent:
        notes = await recon(market, trade_date)
        return await write(notes, market, trade_date)

    async with asyncio.timeout(900):
        content = await RunnableLambda(generate).ainvoke(market, config=config)
    _, model_name = llm_registry.get_or_default(None)
    meta = {
        "duration_ms": int((time.monotonic() - started) * 1000),
        "model_name": model_name,
        "attempts": 1,
    }
    return content, meta
