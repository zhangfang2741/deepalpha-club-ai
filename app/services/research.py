"""行业研究服务：7步顺序执行，每步搜索+LLM结构化输出，以异步生成器流式产出结果."""

import asyncio
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.langgraph.tools.duckduckgo_search import duckduckgo_search_tool
from app.core.logging import logger
from app.schemas.research import (
    BusinessModel,
    IndustryChain,
    IndustryUnderstanding,
    InvestmentView,
    KeyBottlenecks,
    LeadingCompanies,
    WhyItExists,
)
from app.services.llm.service import LLMService

_SYSTEM_PROMPT = """你是一位资深行业研究分析师，擅长对各类行业进行结构化深度分析。

分析要求：
1. 优先基于提供的搜索证据进行分析，无搜索结果时使用你的专业知识
2. 每个结论必须简洁、有据可查
3. evidence 字段中引用实际来源，snippet 为关键摘录，source 为 URL 或搜索来源
4. 严格按照要求的 JSON 格式输出，不要添加额外字段"""

_STEPS = [
    ("understand_industry", "理解行业"),
    ("why_it_exists",       "存在原因"),
    ("industry_chain",      "产业链结构"),
    ("key_bottlenecks",     "核心瓶颈"),
    ("leading_companies",   "龙头企业"),
    ("business_model",      "商业模式"),
    ("investment_view",     "投资观点"),
]


class IndustryResearchService:
    """7步行业研究服务，通过异步生成器流式产出每步结果."""

    def __init__(self) -> None:
        """初始化 LLM 服务."""
        self._llm_service = LLMService()

    async def _search(self, query: str) -> str:
        """执行单条 DuckDuckGo 搜索，失败时静默返回空字符串."""
        try:
            result = await duckduckgo_search_tool.ainvoke(query)
            return str(result) if result else ""
        except Exception as e:
            logger.warning("duckduckgo_search_failed", query=query, error=str(e))
            return ""

    async def _gather_context(self, *queries: str) -> str:
        """并发执行多条搜索，将结果拼接为 context 字符串."""
        results = await asyncio.gather(*[self._search(q) for q in queries], return_exceptions=True)
        parts = []
        for q, r in zip(queries, results, strict=False):
            if isinstance(r, str) and r:
                parts.append(f"[搜索: {q}]\n{r}")
        return "\n\n".join(parts) if parts else "（暂无搜索结果，请基于专业知识回答）"

    def _messages(self, human: str) -> list:
        """构建 LangChain 格式消息列表."""
        return [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=human)]

    async def _step_understand(self, industry: str) -> dict:
        context = await self._gather_context(
            f"{industry} industry overview products customers market size",
            f"{industry} 行业概述 主要产品 客户群体",
        )
        prompt = f"""行业：{industry}

搜索证据：
{context}

请分析该行业，输出字段：
- description：2-3句精准行业定义
- main_products：核心产品或服务类别（3-5项）
- key_customers：主要客户群体类型（3-5项）
- development_stage：当前发展阶段（萌芽/成长/成熟/衰退）及一句理由
- what：一句话说明该行业是什么（面向投资者的精炼表达）
- why：一句话说明理解该行业为何重要
- evidence：从搜索结果提取3-5条关键证据"""
        result = await self._llm_service.call(self._messages(prompt), response_format=IndustryUnderstanding)
        return result.model_dump()

    async def _step_why_it_exists(self, industry: str) -> dict:
        context = await self._gather_context(
            f"{industry} driving forces technology policy demand trend history",
            f"{industry} 行业驱动力 政策 技术 需求",
        )
        prompt = f"""行业：{industry}

搜索证据：
{context}

请分析该行业存在和发展的底层驱动力，输出字段：
- tech_drivers：技术驱动因素列表（如 AI算力、新材料）
- policy_drivers：政策/监管驱动因素列表
- demand_drivers：需求侧驱动因素列表（人口、消费升级等）
- cost_drivers：成本结构变化驱动因素列表
- what：一句话总结最核心驱动力
- why：一句话说明这些驱动力为何重要
- evidence：从搜索结果提取3-5条证据"""
        result = await self._llm_service.call(self._messages(prompt), response_format=WhyItExists)
        return result.model_dump()

    async def _step_industry_chain(self, industry: str) -> dict:
        context = await self._gather_context(
            f"{industry} supply chain upstream downstream value chain",
            f"{industry} 产业链 上游 中游 下游",
        )
        prompt = f"""行业：{industry}

搜索证据：
{context}

请分析该行业产业链结构，输出字段：
- upstream：上游环节（level="上游"，description 描述该环节，key_players 列举代表性参与者）
- midstream：中游环节（同上格式）
- downstream：下游环节（同上格式）
- what：一句话总结产业链核心结构
- why：一句话说明理解产业链对投资者寻找最优环节的意义
- evidence：从搜索结果提取3-5条证据"""
        result = await self._llm_service.call(self._messages(prompt), response_format=IndustryChain)
        return result.model_dump()

    async def _step_key_bottlenecks(self, industry: str) -> dict:
        context = await self._gather_context(
            f"{industry} key bottlenecks constraints pricing power most profitable segment",
            f"{industry} 核心瓶颈 定价权 最赚钱环节",
        )
        prompt = f"""行业：{industry}

搜索证据：
{context}

请分析该行业的核心瓶颈，输出字段：
- bottlenecks：制约行业发展的3-5个核心瓶颈
- pricing_power：产业链中谁拥有定价权及原因（1-2句）
- most_profitable_segment：当前最赚钱的产业链环节及逻辑（1-2句）
- what：一句话总结最关键瓶颈
- why：一句话说明这对投资者的意义
- evidence：从搜索结果提取3-5条证据"""
        result = await self._llm_service.call(self._messages(prompt), response_format=KeyBottlenecks)
        return result.model_dump()

    async def _step_leading_companies(self, industry: str) -> dict:
        context = await self._gather_context(
            f"{industry} leading companies market share competitive landscape top players",
            f"{industry} 龙头公司 市场份额 竞争格局",
        )
        prompt = f"""行业：{industry}

搜索证据：
{context}

请列出该行业主要公司，输出字段：
- companies：3-6家主要公司，每家包含 name、ticker（如有）、business（50字内）、moat（护城河来源）
- what：一句话总结行业竞争格局
- why：一句话说明这些公司为何值得关注
- evidence：从搜索结果提取3-5条证据"""
        result = await self._llm_service.call(self._messages(prompt), response_format=LeadingCompanies)
        return result.model_dump()

    async def _step_business_model(self, industry: str) -> dict:
        context = await self._gather_context(
            f"{industry} business model revenue streams cost structure profit margin",
            f"{industry} 商业模式 收入来源 成本结构 利润率",
        )
        prompt = f"""行业：{industry}

搜索证据：
{context}

请分析该行业的商业模式，输出字段：
- revenue_model：行业典型收入来源和模式（订阅/一次性/服务等）
- cost_structure：主要成本构成（研发/制造/销售/运营等占比描述）
- profit_drivers：利润驱动因素（规模效应/技术壁垒/品牌溢价等）
- moat_sources：护城河来源列表（3-5项）
- what：一句话总结商业模式本质
- why：一句话说明商业模式对估值的影响
- evidence：从搜索结果提取3-5条证据"""
        result = await self._llm_service.call(self._messages(prompt), response_format=BusinessModel)
        return result.model_dump()

    async def _step_investment_view(self, industry: str) -> dict:
        context = await self._gather_context(
            f"{industry} investment opportunity risk outlook 2024 2025 catalyst",
            f"{industry} 投资机会 风险 展望 催化剂",
        )
        prompt = f"""行业：{industry}

搜索证据：
{context}

请给出该行业的投资观点，输出字段：
- opportunities：3-5个具体投资机会（附催化剂和时间窗口）
- risks：3-5个主要风险（系统性/行业特有，需说明影响机制）
- focus_areas：3-4个投资者应重点跟踪的指标或方向
- conclusion：100字以内的综合投资观点总结
- what：一句话总结核心投资逻辑
- why：一句话说明当前时点的特殊性或紧迫性
- evidence：从搜索结果提取3-5条证据"""
        result = await self._llm_service.call(self._messages(prompt), response_format=InvestmentView)
        return result.model_dump()

    async def research_industry(self, industry: str) -> AsyncGenerator[dict, None]:
        """按顺序执行 7 步研究，每步完成后 yield 事件字典."""
        step_fns = [
            self._step_understand,
            self._step_why_it_exists,
            self._step_industry_chain,
            self._step_key_bottlenecks,
            self._step_leading_companies,
            self._step_business_model,
            self._step_investment_view,
        ]
        for idx, ((key, label), fn) in enumerate(zip(_STEPS, step_fns, strict=False)):
            try:
                data = await fn(industry)
                yield {
                    "event": "step",
                    "step_index": idx,
                    "step_key": key,
                    "step_label": label,
                    "data": data,
                    "done": False,
                }
            except Exception as e:
                logger.exception("research_step_failed", step=key, industry=industry, error=str(e))
                yield {
                    "event": "error",
                    "step_index": idx,
                    "step_key": key,
                    "message": f"步骤「{label}」分析失败：{str(e)}",
                    "done": False,
                }
        yield {"event": "done", "industry": industry, "total_steps": 7, "done": True}


industry_research_service = IndustryResearchService()
