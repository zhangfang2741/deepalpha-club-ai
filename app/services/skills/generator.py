"""流式代码生成：SSE 流式输出 LLM 生成的因子代码。"""
from __future__ import annotations

import json
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.logging import logger
from app.services.llm.registry import llm_registry

_SYSTEM_PROMPT = """你是一位量化因子工程师。用户描述一个量化因子，你输出可执行的 Python 函数。

要求：
1. 定义 compute(prices: list[dict], symbol: str) -> list[dict]
2. prices 格式：[{"date": "2024-01-01", "close": 120.5, "open": 119, "high": 122, "low": 118, "volume": 1000000}]
3. 返回格式：list[{"time": "2024-01-01", "value": 0.05}]（value 是原始因子值）
4. 可以使用 numpy（别名 np）和 pandas（别名 pd）以及 math
5. 禁止：os / subprocess / socket / requests / __import__ / eval / exec / open
6. 代码简洁，注释用中文

先用 1-2 句中文说明因子逻辑，再给出完整代码块。
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
