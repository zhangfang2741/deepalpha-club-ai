"""从分析师报告文本抽取 {dir, conf} 信号。

TradingAgents 的分析师只产出大段文字 report，不产出结构化信号；
共识条与流程条上的信号 chip 全靠本模块补齐（spec §4.6）。

约束：
  - 用 quick 档模型（llm_registry 的 TRADING_DESK_QUICK_MODEL 回落默认）
  - 抽取失败降级 neutral 低置信，绝不静默编方向
  - 每份 report 一次调用，约 +4 次/run，计入成本预期
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from app.core.logging import logger

_DEGRADE = ("neutral", 20)


class InvokableLLM(Protocol):
    async def ainvoke(self, prompt: str) -> str: ...


def build_prompt(stage_name: str, report: str) -> str:
    """构造抽取提示词。"""
    return (
        f"你是投研分析助手。下面是「{stage_name}」对某标的的一段分析报告。\n"
        "请只输出一个 JSON 对象（不要任何其他文字），形如：\n"
        '{"dir": "bull|bear|neutral", "conf": 0-100 的整数}\n'
        "dir 表示该报告整体立场（看多/看空/中性），conf 表示立场的明确程度"
        "（越笃定越高，骑墙观点给低分）。\n\n报告内容：\n" + report[:4000]
    )


def _parse_reply(reply: str) -> tuple[str, int] | None:
    """从回复中挖出 JSON。容忍 markdown 代码块包裹。"""
    match = re.search(r"\{[^{}]*\}", reply, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

    direction = str(data.get("dir", "")).lower()
    if direction not in ("bull", "bear", "neutral"):
        return None
    try:
        conf = int(data.get("conf", 0))
    except (TypeError, ValueError):
        return None
    return direction, max(0, min(100, conf))


async def extract_signal(llm: InvokableLLM, *, stage_name: str, report: str) -> tuple[str, int]:
    """抽取信号；任何失败都降级为中性低置信。"""
    if not report.strip():
        return _DEGRADE
    try:
        reply = str(await llm.ainvoke(build_prompt(stage_name, report)))
    except Exception:
        logger.exception("signal_extract_failed", stage=stage_name)
        return _DEGRADE

    parsed = _parse_reply(reply)
    if parsed is None:
        logger.warning("signal_extract_unparseable", stage=stage_name, reply=reply[:200])
        return _DEGRADE
    return parsed


def quick_llm() -> InvokableLLM:
    """取 quick 档模型。延迟导入避免循环依赖。"""
    from app.core.config import settings
    from app.services.llm.registry import llm_registry

    llm, _ = llm_registry.get_or_default(settings.TRADING_DESK_QUICK_MODEL or None)
    return llm  # type: ignore[no-any-return]  # registry 返回 BaseChatModel，兼容 InvokableLLM 协议
