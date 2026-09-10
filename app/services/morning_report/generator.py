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
from pydantic import SecretStr
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
from app.services.morning_report.data_tools import AKSHARE_TOOLS, us_index_snapshot
from app.services.morning_report.prompts import render_prompt
from app.services.morning_report.schema import MorningReportContent

MAX_TOOL_ROUNDS = 6
WRITE_ATTEMPTS = 2
TOOL_RESULT_LIMIT = 4000


def build_tools(market: str) -> list[Any]:
    """按市场选择工具集：us 用 FMP+yfinance（行情兜底）+搜索；cn/hk 用 akshare+搜索。"""
    if market == "us":
        return [
            duckduckgo_search_tool,
            fmp_quote,
            fmp_company_profile,
            fmp_financial_statement,
            us_index_snapshot,
        ]
    return [duckduckgo_search_tool, *AKSHARE_TOOLS]


def _morning_report_llm() -> Any:
    """晨报专用模型：配置了 MORNING_REPORT_OPENAI_API_KEY 时用独立 OpenAI 实例。

    与全局 LLM_PROVIDER/DEFAULT_LLM_MODEL 完全隔离——不进 registry、不影响
    聊天 Agent/供应链/因子探索，也不受 DEFAULT_LLM_MODEL 变化影响。
    未配置时退回全局默认模型（向后兼容，原有行为不变）。
    """
    if not settings.MORNING_REPORT_OPENAI_API_KEY:
        return llm_registry.get_default()
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.MORNING_REPORT_OPENAI_MODEL,
        api_key=SecretStr(settings.MORNING_REPORT_OPENAI_API_KEY),
    )


def _recon_llm(market: str) -> Any:
    """取晨报专用模型实例 + 绑市场工具（测试 monkeypatch 点）。

    注意：不能用 llm_service.bind_tools()——它会把工具绑定写回全局单例
    self._llm，污染聊天 Agent 的默认模型。bind_tools 返回值是全新的
    RunnableBinding，不影响共享实例。
    """
    return _morning_report_llm().bind_tools(build_tools(market))


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
    response = await _morning_report_llm().ainvoke(messages)
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
                messages = [
                    SystemMessage(content=prompt),
                    HumanMessage(content=f"调研笔记：\n{notes}\n\n请输出晨报 JSON。{error_hint}"),
                ]
                if settings.MORNING_REPORT_OPENAI_API_KEY:
                    # 专用 key：走独立 OpenAI 实例，不经过 llm_service.call 的
                    # registry fallback（只有一个模型，fallback 无意义）。
                    structured_llm = _morning_report_llm().with_structured_output(
                        MorningReportContent
                    )
                    result = await asyncio.wait_for(
                        structured_llm.ainvoke(messages), timeout=300
                    )
                else:
                    result = await llm_service.call(
                        messages=messages,
                        response_format=MorningReportContent,
                        timeout=300,
                    )
                if result is None:
                    # 模型未触发结构化输出时 with_structured_output 会静默返回 None
                    # （不抛异常）——必须显式转成错误，否则会被当成功返回，
                    # 下游 content.model_dump() 对 None 崩溃且任务不落 failed 状态。
                    raise ValueError("模型未返回结构化晨报内容（response_format 解析为空）")
                return result
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
