"""八字 AI 解读：daily(免费今日运势) / deep(付费深度解读) 两档文案生成。"""

from typing import Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.prompts.bazi import DAILY_PROMPT, DEEP_PROMPT
from app.schemas.bazi import (
    BaziChartRequest,
    BaziChartResponse,
    InterpretationRequest,
    InterpretationResponse,
    Pillar,
)
from app.services.bazi.chart import build_bazi_chart
from app.services.llm import llm_service

_GENDER_LABEL = {"male": "男", "female": "女"}
_SECTION_PROMPT = {"daily": DAILY_PROMPT, "deep": DEEP_PROMPT}


def _describe_pillar(name: str, pillar: Optional[Pillar]) -> str:
    if pillar is None:
        return f"{name}：未知（出生时辰不确定）"
    shi_shen_zhi = "、".join(pillar.shi_shen_zhi)
    return f"{name}：{pillar.gan}{pillar.zhi}（纳音：{pillar.na_yin}，十神：{pillar.shi_shen_gan}/{shi_shen_zhi}）"


def _describe_chart(chart: BaziChartResponse, gender: Literal["male", "female"]) -> str:
    wu_xing_line = "、".join(f"{k}{v}" for k, v in chart.wu_xing_distribution.items())
    da_yun_line = "、".join(f"{d.gan_zhi}({d.start_age}-{d.end_age}岁)" for d in chart.da_yun)
    return "\n".join(
        [
            f"性别：{_GENDER_LABEL[gender]}",
            f"阳历生日：{chart.solar_date}",
            f"农历：{chart.lunar_date}",
            _describe_pillar("年柱", chart.year_pillar),
            _describe_pillar("月柱", chart.month_pillar),
            _describe_pillar("日柱", chart.day_pillar),
            _describe_pillar("时柱", chart.time_pillar),
            f"五行分布：{wu_xing_line}",
            f"大运：{da_yun_line}",
            f"今年流年：{chart.liu_nian_gan_zhi}",
        ]
    )


async def generate_interpretation(request: InterpretationRequest) -> InterpretationResponse:
    """调用 AI 生成今日运势(daily)或深度解读(deep)文案。"""
    chart = build_bazi_chart(
        BaziChartRequest(
            birth_date=request.birth_date,
            birth_time=request.birth_time,
            birth_city=request.birth_city,
            gender=request.gender,
        )
    )
    chart_description = _describe_chart(chart, request.gender)
    result = await llm_service.call(
        [
            SystemMessage(content=_SECTION_PROMPT[request.section]),
            HumanMessage(content=chart_description),
        ]
    )
    return InterpretationResponse(text=_extract_message_text(result.content))


def _extract_message_text(content: object) -> str:
    """从 LLM 响应中只提取正文文本。

    不同供应商的 ``AIMessage.content`` 形态不同：
    - OpenAI 等：直接是 ``str``。
    - Claude（开启 extended thinking）等：是内容块列表，例如
      ``[{"type": "thinking", ...}, {"type": "text", "text": "..."}]``。
    直接 ``str(content)`` 会把 thinking / signature 等原始块也当成正文，
    因此这里只保留 text 块，丢弃 thinking / reasoning 等推理块。
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                block_type = block.get("type")
                if block_type in {"thinking", "reasoning", "redacted_thinking"}:
                    continue
                text = block.get("text")
                if isinstance(text, str) and text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return str(content).strip()
