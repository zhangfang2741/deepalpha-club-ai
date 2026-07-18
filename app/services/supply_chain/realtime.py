"""Build and stream an ephemeral supply-chain graph directly from the LLM."""

import asyncio
import json
import re
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.observability import langfuse_callback_handler
from app.services.llm.registry import llm_registry
from app.services.llm.service import llm_service
from app.services.supply_chain.alias_resolver import normalize_alias
from app.services.supply_chain.discover import (
    DiscoveryResult,
    StructuredLLM,
    SupplyRelation,
    discover_suppliers,
)
from app.services.supply_chain.domain import GiraffeEdge, GiraffeGraph, GiraffeNode, GiraffeProperty
from app.services.supply_chain.product_taxonomy import normalize_product
from app.utils.uuid_util import generate_uuid_from_str


def _properties(**values: object) -> list[GiraffeProperty]:
    return [GiraffeProperty(name=name, value=value) for name, value in values.items()]


def _node_id(ticker: str | None, name: str) -> str:
    """Use a listed ticker as identity, falling back to a canonical-name UUID."""
    return ticker or generate_uuid_from_str(normalize_alias(name))


def _relation_properties(relation: SupplyRelation) -> list[GiraffeProperty]:
    products = relation.products
    product_text = relation.product_text
    return _properties(
        product=" / ".join(product.short_name for product in products) or product_text,
        product_text=product_text,
        products=[product.model_dump() for product in products],
        product_category=normalize_product(product_text),
        confidence=relation.confidence,
        confidence_source="LLM",
        status="preview",
        rationale=relation.rationale,
        relationship_description=relation.relationship_description,
        relationship_description_zh=relation.relationship_description_zh,
        is_single_source=relation.is_single_source,
    )


def build_realtime_graph(ticker: str, result: DiscoveryResult) -> GiraffeGraph:
    """Convert structured discovery output to a deduplicated in-memory graph."""
    target_ticker = ticker.upper()
    target = GiraffeNode(
        node_id=target_ticker,
        node_type="company",
        properties=_properties(
            name=target_ticker,
            name_zh=result.company_name_zh,
            ticker=target_ticker,
            resolved=True,
            is_listed=True,
            expandable=True,
        ),
    )
    nodes: dict[str, GiraffeNode] = {target_ticker: target}
    edges: dict[str, GiraffeEdge] = {}

    for relation in result.suppliers[:5]:
        if not relation.supplier_name:
            continue
        node_id = _node_id(relation.supplier_ticker, relation.supplier_name)
        supplier = GiraffeNode(
            node_id=node_id,
            node_type="supplier",
            properties=_properties(
                name=relation.supplier_name,
                name_zh=relation.supplier_name_zh,
                ticker=relation.supplier_ticker,
                resolved=relation.supplier_ticker is not None,
                is_listed=relation.supplier_ticker is not None,
                expandable=relation.supplier_ticker is not None,
            ),
        )
        nodes[node_id] = supplier
        edge = GiraffeEdge(
            src_type="supplier",
            src_id=node_id,
            dst_type="company",
            dst_id=target_ticker,
            edge_type="SUPPLIED_BY",
            properties=_relation_properties(relation),
        )
        edges[str(edge.edge_id)] = edge

    for relation in result.customers[:5]:
        if not relation.customer_name:
            continue
        node_id = _node_id(relation.customer_ticker, relation.customer_name)
        customer = GiraffeNode(
            node_id=node_id,
            node_type="company",
            properties=_properties(
                name=relation.customer_name,
                name_zh=relation.customer_name_zh,
                ticker=relation.customer_ticker,
                resolved=relation.customer_ticker is not None,
                is_listed=relation.customer_ticker is not None,
                expandable=relation.customer_ticker is not None,
            ),
        )
        nodes[node_id] = customer
        edge = GiraffeEdge(
            src_type="company",
            src_id=target_ticker,
            dst_type="company",
            dst_id=node_id,
            edge_type="CUSTOMER_OF",
            properties=_relation_properties(relation),
        )
        edges[str(edge.edge_id)] = edge

    return GiraffeGraph(graph_id=target_ticker, nodes=list(nodes.values()), edges=list(edges.values()))


async def generate_realtime_graph(ticker: str, llm: StructuredLLM) -> GiraffeGraph:
    """Generate a graph without database reads, writes, or background tasks."""
    result = await discover_suppliers(ticker, llm)
    return build_realtime_graph(ticker, result)


async def stream_realtime_graph(ticker: str) -> AsyncGenerator[dict, None]:
    """Stream raw model output, followed by one validated graph event."""
    normalized_ticker = ticker.upper()
    yield {"type": "status", "content": f"正在请求 MiniMax 分析 {normalized_ticker}…\n"}
    prompt = f"""Build a concise real-time supply-chain graph for US ticker {normalized_ticker}.
Return JSON only, without Markdown, using exactly this compact schema:
{{
  "company_name_zh": "...",
  "suppliers": [{{
    "supplier_name": "official English company name",
    "supplier_name_zh": "简体中文名",
    "supplier_ticker": "primary US ticker or null",
    "product_text": "concise supplied product or service",
    "rationale": "one concise sentence explaining why this is a core relationship",
    "confidence": 0,
    "is_single_source": false,
    "info_year": 2026
  }}],
  "customers": [{{
    "customer_name": "official English company name",
    "customer_name_zh": "简体中文名",
    "customer_ticker": "primary US ticker or null",
    "product_text": "concise purchased product or service",
    "rationale": "one concise sentence explaining why this is a major customer",
    "confidence": 0,
    "is_single_source": false,
    "info_year": 2026
  }}],
  "skipped": false,
  "skip_reason": null
}}
Return at most 5 genuinely core direct suppliers and 5 major direct customers. Never pad lists.
US-listed companies must use their primary NASDAQ/NYSE/AMEX ticker; use null for private, non-US,
or uncertain listings. Never repeat a ticker. TSMC is TSM, not SMECF. Confidence is factual certainty.
Keep product_text and rationale short. Do not output products or long descriptions."""
    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=f"Generate the real-time supply-chain graph for {normalized_ticker}."),
    ]
    callbacks: list[BaseCallbackHandler] = (
        [langfuse_callback_handler] if settings.LANGFUSE_TRACING_ENABLED else []
    )
    config: RunnableConfig = {"callbacks": callbacks}
    chunks: list[str] = []
    llm, resolved_model = llm_registry.get_or_default(
        settings.SUPPLY_CHAIN_DISCOVER_MODEL or settings.DEFAULT_LLM_MODEL
    )
    # 队列项：{"kind": "answer"|"thinking", "text": str} | BaseException | None
    queue: asyncio.Queue[dict[str, str] | BaseException | None] = asyncio.Queue()

    def _split_chunk(chunk: Any) -> tuple[str, str]:
        """从流式 chunk 中拆出答案文本与思考文本.

        推理型模型（如 MiniMax-M2.7）会先流式输出 thinking/reasoning 块再输出答案；
        原实现只取 text 块，导致思考阶段几十秒「零输出」。这里同时捕获思考内容。
        """
        answer, thinking = "", ""
        content = chunk.content
        if isinstance(content, str):
            answer = content
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    answer += str(block)
                    continue
                btype = block.get("type")
                if btype in ("thinking", "reasoning"):
                    thinking += str(block.get("thinking") or block.get("reasoning") or block.get("text") or "")
                else:
                    answer += str(block.get("text", ""))
        # 兜底：部分实现把推理放在 additional_kwargs.reasoning_content
        if not thinking:
            extra = getattr(chunk, "additional_kwargs", None)
            if isinstance(extra, dict) and isinstance(extra.get("reasoning_content"), str):
                thinking = extra["reasoning_content"]
        return answer, thinking

    async def produce() -> None:
        try:
            async for chunk in llm.astream(messages, config=config):
                answer, thinking = _split_chunk(chunk)
                if thinking:
                    await queue.put({"kind": "thinking", "text": thinking})
                if answer:
                    await queue.put({"kind": "answer", "text": answer})
        except BaseException as error:
            await queue.put(error)
        finally:
            await queue.put(None)

    producer = asyncio.create_task(produce())
    waited_seconds = 0
    received_any = False
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=3)
            except TimeoutError:
                waited_seconds += 3
                if not received_any:
                    yield {
                        "type": "status",
                        "content": f"MiniMax 正在分析 {normalized_ticker}，已等待 {waited_seconds} 秒…\n",
                    }
                continue
            if item is None:
                break
            if isinstance(item, BaseException):
                raise item
            received_any = True
            # 思考内容仅用于实时展示进度，不计入最终 JSON 解析
            if item["kind"] == "answer":
                chunks.append(item["text"])
            yield {"type": "delta", "content": item["text"]}
    finally:
        if not producer.done():
            producer.cancel()
        await asyncio.gather(producer, return_exceptions=True)

    content = "".join(chunks)
    try:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match is None:
            raise ValueError("model returned no parseable JSON")
        result = DiscoveryResult.model_validate(json.loads(match.group(0)))
    except (json.JSONDecodeError, ValueError):
        yield {
            "type": "status",
            "content": "MiniMax 流式 JSON 不完整，正在自动整理结构化结果…\n",
        }
        repaired = await llm_service.call(
            messages,
            model_name=resolved_model,
            response_format=DiscoveryResult,
        )
        result = (
            repaired
            if isinstance(repaired, DiscoveryResult)
            else DiscoveryResult.model_validate(repaired)
        )
    graph = build_realtime_graph(normalized_ticker, result)
    yield {"type": "result", "graph": graph.to_dict()}
