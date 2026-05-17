"""AI 旁白生成：将因子快照（信号点 + 指标卡）转化为业务语言叙事。"""
from __future__ import annotations

import json
from datetime import UTC, datetime

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.logging import logger
from app.services.llm.registry import llm_registry

_NARRATOR_PROMPT = """你是一位资深量化研究员，为股票因子计算结果撰写专业旁白。

要求：
1. 语言：业务化、自然流畅，禁止出现"Python/代码/函数/变量"等技术词汇
2. 三段式：立意 + 关键时点 + 适用失效场景
3. 关键时点旁白：每条 20-40 字，描述当时市场背景与因子含义
4. 适用/失效场景：各 1-2 句

严格按以下 JSON 格式输出，不要加 markdown fence：
{
  "thesis": "一句话立意",
  "key_points": [{"date": "YYYY-MM-DD", "z": 2.5, "text": "市场背景（20-40字）"}],
  "verdict": {"applicable": "适用场景", "fails": "失效场景"}
}
"""


async def generate_narrative(
    snapshot: dict,
    symbol: str,
    category: str,
) -> dict:
    """根据因子快照生成 AI 旁白，返回 narrative dict。"""
    llm = llm_registry.get_default()

    signals = snapshot.get("signals", [])
    metrics = snapshot.get("metrics", {})
    factor = snapshot.get("factor", [])

    lines = [
        f"股票：{symbol}  因子类别：{category}",
        f"当前 z-score：{metrics.get('current_z', 'N/A')}  峰值 z-score：{metrics.get('peak_z', 'N/A')}",
        f"触发极端信号次数（|z|≥1.0）：{metrics.get('trigger_count', 0)}  数据天数：{metrics.get('data_days', 0)}",
        "",
        "关键信号点：",
    ]
    for s in signals:
        lines.append(f"  {s['date']}  z={s['z']:+.2f}  收盘价={s.get('close', 'N/A')}")

    lines += ["", "因子时序（首尾各10点）："]
    for f in factor[:10]:
        lines.append(f"  {f['time']}  {f['value']:+.4f}")
    if len(factor) > 20:
        lines.append("  ...")
        for f in factor[-10:]:
            lines.append(f"  {f['time']}  {f['value']:+.4f}")

    user_content = "\n".join(lines)

    msgs = [SystemMessage(content=_NARRATOR_PROMPT), HumanMessage(content=user_content)]
    logger.info("narrator_generate_start", symbol=symbol, category=category)

    response = await llm.ainvoke(msgs)
    raw = response.content.strip()

    # 清理可能的 markdown fence
    for fence in ("```json\n", "```\n", "```json", "```"):
        if raw.startswith(fence):
            raw = raw[len(fence):]
        if raw.endswith("```"):
            raw = raw[:-3]
    raw = raw.strip()

    try:
        narrative = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("narrator_parse_failed", raw=raw[:200])
        narrative = {
            "thesis": f"{symbol} 因子分析",
            "key_points": [
                {"date": s["date"], "z": s["z"],
                 "text": f"z-score {s['z']:+.2f}，当时收盘价 {s.get('close', 'N/A')}"}
                for s in signals
            ],
            "verdict": {"applicable": "趋势行情", "fails": "震荡市"},
        }

    narrative["generated_at"] = datetime.now(UTC).isoformat()
    narrative["model"] = getattr(llm, "model_name", "unknown")
    return narrative
