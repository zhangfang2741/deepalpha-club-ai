"""LLM 驱动的句子级事实抽取服务。

将文本 chunk 转化为结构化三元组（实体 + 关系 + 原文证据），
映射至四类 Schema：HAS_PRODUCT / SUPPLIED_BY / ENABLED_BY / CONSTRAINED_BY。
"""

import json
import re
from datetime import datetime
from typing import Any, Optional

from app.core.logging import logger
from app.models.graph_entity import EntityType
from app.models.graph_fact import RelationType
from app.services.graph.normalizer import guess_entity_type, normalize_entity_name

_SYSTEM_PROMPT = """You are a financial research assistant specialized in extracting structured supply chain facts from SEC filings and earnings call transcripts about the NVIDIA AI infrastructure ecosystem.

Extract relationship triples between entities. Focus ONLY on the NVIDIA supply chain ecosystem.

## Entity Types
- Company: Organizations (e.g., NVIDIA, TSMC, Microsoft, SK Hynix, Meta, Vertiv, Broadcom)
- Product: Specific products or product lines (e.g., H100, A100, HBM3, CoWoS packages, DGX systems)
- Technology: Technical capabilities (e.g., CUDA, HBM, CoWoS, NVLink, Transformer Engine, InfiniBand)
- Concept: Demand/market concepts (e.g., AI Training, AI Inference, Generative AI, Large Language Models)
- Resource: Supply or constraint factors (e.g., Power Capacity, CoWoS Packaging Capacity, HBM Supply, Wafer Capacity)

## Relationship Types (choose EXACTLY one)
- HAS_PRODUCT: Company → Product (company owns/defines/manufactures a product)
- SUPPLIED_BY: Product/Technology/Resource → Company (company supplies or manufactures)
- ENABLED_BY: Concept/Product → Technology/Resource (requires this capability or resource)
- CONSTRAINED_BY: Product/Concept/System → Resource/Technology (bottleneck or limitation)

## Rules
1. Extract ONLY facts explicitly stated or strongly implied in the text
2. Each fact must include the exact evidence sentence from the text
3. Assign confidence (0.0-1.0) based on how explicitly the fact is stated
4. Extract event_time (YYYY-MM-DD or YYYY-QN format) only if the text mentions a specific time period
5. Skip generic/vague statements; focus on concrete supply chain relationships
6. Return empty facts array if no relevant facts found

## Output Format
Return ONLY valid JSON (no markdown, no explanation):
{
  "facts": [
    {
      "source_entity": {"name": "NVIDIA", "type": "Company"},
      "relation": "HAS_PRODUCT",
      "target_entity": {"name": "H100", "type": "Product"},
      "evidence": "NVIDIA's H100 Tensor Core GPU is the cornerstone of the company's data center business.",
      "confidence": 0.95,
      "event_time": null
    }
  ]
}"""


def _build_user_prompt(chunk_text: str, source_info: str) -> str:
    """构建用户提示词。"""
    return f"""Source: {source_info}

Text chunk to analyze:
---
{chunk_text}
---

Extract supply chain facts from this text. Return JSON only."""


def _parse_llm_response(response_text: str) -> list[dict[str, Any]]:
    """解析 LLM 返回的 JSON，鲁棒处理 markdown 代码块包裹。"""
    text = response_text.strip()
    # 去除 markdown 代码块
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("facts", [])
    except json.JSONDecodeError:
        # 尝试提取 JSON 对象
        match = re.search(r'\{.*"facts"\s*:\s*\[.*?\]\s*\}', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                return data.get("facts", [])
            except json.JSONDecodeError:
                pass
    logger.warning("llm_response_parse_failed", raw_text=text[:200])
    return []


class ExtractedFact:
    """单条抽取事实，携带规范化实体名称与类型。"""

    def __init__(  # noqa: D107
        self,
        source_name: str,
        source_type: EntityType,
        relation: RelationType,
        target_name: str,
        target_type: EntityType,
        evidence_text: str,
        confidence: float,
        event_time: Optional[datetime],
    ):
        self.source_name = source_name
        self.source_type = source_type
        self.relation = relation
        self.target_name = target_name
        self.target_type = target_type
        self.evidence_text = evidence_text
        self.confidence = confidence
        self.event_time = event_time


def _parse_event_time(raw: Optional[str]) -> Optional[datetime]:
    """将字符串转换为 datetime（宽松解析，季度格式兜底到季度首日）。"""
    if not raw:
        return None
    raw = str(raw).strip()
    # 标准日期
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%Y"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    # 季度格式 2024-Q3 / Q3 2024
    m = re.match(r"(\d{4})[- ]?Q([1-4])", raw, re.IGNORECASE)
    if not m:
        m = re.match(r"Q([1-4])[- ]?(\d{4})", raw, re.IGNORECASE)
        if m:
            q, y = int(m.group(1)), int(m.group(2))
        else:
            return None
    else:
        y, q = int(m.group(1)), int(m.group(2))
    month = (q - 1) * 3 + 1
    return datetime(y, month, 1)


def _map_entity_type(raw_type: str) -> EntityType:
    """将字符串类型映射为枚举值，不认识的默认 Company。"""
    mapping = {
        "company": EntityType.COMPANY,
        "product": EntityType.PRODUCT,
        "technology": EntityType.TECHNOLOGY,
        "concept": EntityType.CONCEPT,
        "resource": EntityType.RESOURCE,
    }
    return mapping.get(raw_type.lower(), EntityType.COMPANY)


def _map_relation_type(raw_relation: str) -> Optional[RelationType]:
    """将字符串关系类型映射为枚举值，未知返回 None（跳过该 fact）。"""
    mapping = {
        "has_product": RelationType.HAS_PRODUCT,
        "supplied_by": RelationType.SUPPLIED_BY,
        "enabled_by": RelationType.ENABLED_BY,
        "constrained_by": RelationType.CONSTRAINED_BY,
    }
    return mapping.get(raw_relation.lower().replace(" ", "_").replace("-", "_"))


def parse_extracted_facts(raw_facts: list[dict[str, Any]]) -> list[ExtractedFact]:
    """将 LLM 返回的原始 dict 列表转化为 ExtractedFact 对象列表。"""
    results: list[ExtractedFact] = []
    for raw in raw_facts:
        try:
            src_raw = raw.get("source_entity", {})
            tgt_raw = raw.get("target_entity", {})
            relation_str = raw.get("relation", "")

            relation = _map_relation_type(relation_str)
            if relation is None:
                logger.warning("unknown_relation_type", raw_relation=relation_str)
                continue

            src_name = normalize_entity_name(src_raw.get("name", ""))
            tgt_name = normalize_entity_name(tgt_raw.get("name", ""))

            if not src_name or not tgt_name:
                continue

            src_type_raw = src_raw.get("type") or guess_entity_type(src_name)
            tgt_type_raw = tgt_raw.get("type") or guess_entity_type(tgt_name)

            results.append(ExtractedFact(
                source_name=src_name,
                source_type=_map_entity_type(src_type_raw),
                relation=relation,
                target_name=tgt_name,
                target_type=_map_entity_type(tgt_type_raw),
                evidence_text=raw.get("evidence", "")[:2000],
                confidence=float(raw.get("confidence", 0.8)),
                event_time=_parse_event_time(raw.get("event_time")),
            ))
        except Exception as e:
            logger.warning("fact_parse_error", error=str(e), raw=str(raw)[:200])
            continue

    return results


async def extract_facts_from_chunk(
    chunk_text: str,
    source_info: str,
    llm_client: Any,
) -> list[ExtractedFact]:
    """从单个文本 chunk 中抽取供应链事实三元组。

    Args:
        chunk_text: 800-1500 tokens 的文本块
        source_info: 来源描述（如 "NVIDIA 10-K 2024, Risk Factors"）
        llm_client: LangChain BaseChatModel 实例

    Returns:
        抽取到的事实列表
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=_build_user_prompt(chunk_text, source_info)),
    ]

    try:
        response = await llm_client.ainvoke(messages)
        raw_text = response.content if hasattr(response, "content") else str(response)
        raw_facts = _parse_llm_response(raw_text)
        facts = parse_extracted_facts(raw_facts)
        logger.info(
            "facts_extracted_from_chunk",
            chunk_len=len(chunk_text),
            source=source_info[:80],
            fact_count=len(facts),
        )
        return facts
    except Exception as e:
        logger.exception("fact_extraction_failed", source=source_info[:80], error=str(e))
        return []
