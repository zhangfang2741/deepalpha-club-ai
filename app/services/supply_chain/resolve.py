"""Resolve discovery output into a persisted property graph."""

import time
import uuid

from sqlmodel import Session

from app.services.supply_chain.alias_resolver import normalize_alias
from app.services.supply_chain.discover import DiscoveryResult, SupplyRelation
from app.services.supply_chain.domain import GiraffeEdge, GiraffeGraph, GiraffeNode, GiraffeProperty
from app.services.supply_chain.fmp_universe import FMPUniverse, ListedCompany
from app.services.supply_chain.product_taxonomy import normalize_product
from app.services.supply_chain.repository import SupplyChainRepository
from app.utils.uuid_util import generate_uuid_from_str


def _props(**values: object) -> list[GiraffeProperty]:
    return [GiraffeProperty(name=name, value=value) for name, value in values.items()]


def _resolved_node(name: str, node_type: str, universe: FMPUniverse, name_zh: str | None = None) -> GiraffeNode:
    canonical = normalize_alias(name)
    match = universe.match(canonical)
    node_id = match.symbol if match else generate_uuid_from_str(canonical)
    return GiraffeNode(
        node_id=node_id,
        node_type=node_type,
        properties=_props(
            name=match.name if match else canonical,
            name_zh=name_zh,
            ticker=match.symbol if match else None,
            aliases=[name] if name != canonical else [],
            resolved=match is not None,
            is_listed=match is not None,
            expandable=match is not None,
            market_cap=match.market_cap if match else None,
        ),
    )


def _edge(source: GiraffeNode, target: GiraffeNode, edge_type: str, relation: SupplyRelation) -> GiraffeEdge:
    products = [product.model_dump() for product in relation.products]
    short_product = " / ".join(product.short_name for product in relation.products) or relation.product_text
    return GiraffeEdge(
        src_type=source.node_type,
        src_id=source.node_id,
        dst_type=target.node_type,
        dst_id=target.node_id,
        edge_type=edge_type,
        timestamp=int(time.time()),
        properties=_props(
            product=short_product,
            product_text=relation.product_text,
            products=products,
            product_category=normalize_product(relation.product_text),
            confidence=relation.confidence,
            confidence_source="LLM",
            status="active",
            rationale=relation.rationale,
            relationship_description=relation.relationship_description,
            relationship_description_zh=relation.relationship_description_zh,
            evidence_summary="",
            is_single_source=relation.is_single_source,
            changed=False,
        ),
    )


def resolve_suppliers(
    ticker: str,
    result: DiscoveryResult,
    session: Session,
    universe: FMPUniverse,
    run_id: uuid.UUID | None = None,
) -> GiraffeGraph:
    """Resolve aliases/tickers/products, build a graph, and upsert it."""
    ticker = ticker.upper()
    buyer_match = universe.match(ticker) or ListedCompany(ticker, ticker)
    buyer = _resolved_node(buyer_match.name, "company", universe, result.company_name_zh)
    if buyer.node_id != ticker:
        buyer.node_id = ticker
    nodes: dict[str, GiraffeNode] = {str(buyer.node_id): buyer}
    edges: list[GiraffeEdge] = []
    for relation in result.suppliers:
        if not relation.supplier_name:
            continue
        supplier = _resolved_node(relation.supplier_name, "supplier", universe, relation.supplier_name_zh)
        nodes[str(supplier.node_id)] = supplier
        edges.append(_edge(supplier, buyer, "SUPPLIED_BY", relation))
    for relation in result.customers:
        if not relation.customer_name:
            continue
        customer = _resolved_node(relation.customer_name, "company", universe, relation.customer_name_zh)
        nodes[str(customer.node_id)] = customer
        edges.append(_edge(buyer, customer, "CUSTOMER_OF", relation))
    graph = GiraffeGraph(graph_id=ticker, nodes=list(nodes.values()), edges=edges)
    SupplyChainRepository(session).upsert_graph(graph, run_id)
    return graph
