"""Build and stream an ephemeral supply-chain graph directly from the LLM."""

import asyncio
import json
import re
from collections.abc import AsyncGenerator
from typing import Any, Optional

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
    parse_discovery_result,
)
from app.services.supply_chain.domain import GiraffeEdge, GiraffeGraph, GiraffeNode, GiraffeProperty
from app.services.supply_chain.product_taxonomy import normalize_product
from app.utils.uuid_util import generate_uuid_from_str

TARGET_COMPANY_ALIASES = {
    "FIG": {"ticker": "FIG", "name": "Figma, Inc.", "name_zh": "Figma"},
    "FIGMA": {"ticker": "FIG", "name": "Figma, Inc.", "name_zh": "Figma"},
}


def _properties(**values: object) -> list[GiraffeProperty]:
    return [GiraffeProperty(name=name, value=value) for name, value in values.items()]


def _node_id(ticker: str | None, name: str) -> str:
    """Use a listed ticker as identity, falling back to a canonical-name UUID."""
    return ticker or generate_uuid_from_str(normalize_alias(name))


def _is_chinese_reasoning(text: str) -> bool:
    """Return whether a reasoning chunk is predominantly useful Chinese text."""
    chinese_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    return chinese_count >= 4 and chinese_count * 2 >= latin_count


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
    input_ticker = ticker.upper()
    known_company = TARGET_COMPANY_ALIASES.get(input_ticker)
    target_ticker = known_company["ticker"] if known_company else result.target_ticker or input_ticker
    target = GiraffeNode(
        node_id=target_ticker,
        node_type="company",
        properties=_properties(
            name=known_company["name"] if known_company else target_ticker,
            name_zh=known_company["name_zh"] if known_company else result.company_name_zh,
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


async def stream_realtime_graph(
    ticker: str, model_name: Optional[str] = None
) -> AsyncGenerator[dict, None]:
    """Stream raw model output, followed by one validated graph event.

    model_name 为调用方（按当前用户偏好）解析出的模型名；优先级高于
    SUPPLY_CHAIN_DISCOVER_MODEL / DEFAULT_LLM_MODEL。
    """
    input_ticker = ticker.upper()
    known_company = TARGET_COMPANY_ALIASES.get(input_ticker)
    normalized_ticker = known_company["ticker"] if known_company else input_ticker
    known_identity = (
        f"目标公司已确认是 {known_company['name']}，当前主要美股代码是 {known_company['ticker']}。"
        "绝不能识别成 FormFactor；FormFactor 是另一家公司，代码为 FORM。"
        if known_company
        else "请先准确识别目标公司的官方名称和当前主要美股代码。"
    )
    yield {"type": "status", "content": f"正在请求 MiniMax 分析 {normalized_ticker}…\n"}
    prompt = f"""用户原始输入是 {input_ticker}。{known_identity}
请为该目标公司构建一份精简的实时供应链图谱。

【最高优先级语言规则】你的全部 thinking、reasoning、分析过程和最终说明都必须使用简体中文。
除公司官方英文名、ticker、JSON key 外，不得输出英文单词或英文完整句子。即使内部默认使用英文思考，也必须先翻译成简体中文再输出。

【语言要求】全程用**简体中文**进行思考（reasoning/thinking）与说明；JSON 中除公司官方英文名
（*_name 字段）与美股 ticker 代码保持英文外，其余文本字段（product_text、rationale 等）一律用简体中文。

只返回 JSON，不要 Markdown，严格使用如下紧凑结构：
{{
  "target_ticker": "目标公司的主要美股代码",
  "company_name_zh": "公司简体中文名",
  "suppliers": [{{
    "supplier_name": "公司官方英文名",
    "supplier_name_zh": "简体中文名",
    "supplier_ticker": "主要美股代码或 null",
    "product_text": "供应的具体产品或服务（简体中文，简洁）",
    "rationale": "一句话说明为何是核心供应关系（简体中文）",
    "relationship_description_zh": "两句以内、针对该具体供应商的说明：它向目标公司供应什么、用在何处、为何关键（简体中文，避免套话）",
    "confidence": 85,
    "is_single_source": false,
    "info_year": 2026
  }}],
  "customers": [{{
    "customer_name": "公司官方英文名",
    "customer_name_zh": "简体中文名",
    "customer_ticker": "主要美股代码或 null",
    "product_text": "采购的具体产品或服务（简体中文，简洁）",
    "rationale": "一句话说明为何是主要客户（简体中文）",
    "relationship_description_zh": "两句以内、针对该具体客户的说明：它向目标公司采购什么、用于什么业务、为何重要（简体中文，避免套话）",
    "confidence": 85,
    "is_single_source": false,
    "info_year": 2026
  }}],
  "skipped": false,
  "skip_reason": null
}}
最多返回 5 个真正核心的直接供应商与 5 个主要直接客户，绝不凑数。
target_ticker 必须是目标公司的当前主要 NASDAQ/NYSE/AMEX 代码，例如用户输入 FIGMA 时返回 FIG。
美股公司必须用其主要 NASDAQ/NYSE/AMEX 代码；私有、非美股或不确定的用 null。不要重复 ticker。
台积电是 TSM，不是 SMECF。confidence 表示事实确定度，必须填写 50 到 100 的整数百分比（例如 85），禁止填写 0.85；低于 50 的推测关系不要返回。product_text 与 rationale 保持简短，不要输出 products 字段。
每条关系的 relationship_description_zh 必须**针对该具体公司与产品**、彼此不同，禁止使用「构成两家公司之间的直接业务与供应链联系」这类通用套话。"""
    messages = [
        SystemMessage(content=prompt),
        HumanMessage(
            content=f"请用简体中文思考并生成 {input_ticker}（目标代码 {normalized_ticker}）的实时供应链图谱。"
        ),
    ]
    callbacks: list[BaseCallbackHandler] = (
        [langfuse_callback_handler] if settings.LANGFUSE_TRACING_ENABLED else []
    )
    config: RunnableConfig = {"callbacks": callbacks}
    chunks: list[str] = []
    llm, resolved_model = llm_registry.get_or_default(
        model_name or settings.SUPPLY_CHAIN_DISCOVER_MODEL or settings.DEFAULT_LLM_MODEL
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
    foreign_reasoning_notified = False
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
            elif not _is_chinese_reasoning(item["text"]):
                if not foreign_reasoning_notified:
                    foreign_reasoning_notified = True
                    yield {
                        "type": "status",
                        "content": f"MiniMax 正在分析 {normalized_ticker} 的核心供应商与客户…\n",
                    }
                continue
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
        result = parse_discovery_result(repaired)
        if result is None:
            raw_repaired = await llm_service.call(
                messages,
                model_name=resolved_model,
            )
            result = parse_discovery_result(raw_repaired)
        if result is None:
            raise ValueError("MiniMax 未返回可解析的供应链 JSON")
    graph = build_realtime_graph(normalized_ticker, result)
    yield {"type": "result", "graph": graph.to_dict()}
