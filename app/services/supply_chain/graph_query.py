"""Bounded multi-hop graph queries."""

from dataclasses import dataclass
from threading import RLock
from time import monotonic

from sqlalchemy import or_
from sqlalchemy.orm import aliased
from sqlmodel import Session, col, select

from app.models.supply_chain_edge import SupplyChainEdge
from app.models.supply_chain_node import SupplyChainNode
from app.services.supply_chain.domain import GiraffeEdge, GiraffeGraph, GiraffeNode, GiraffeProperty


@dataclass(frozen=True)
class GraphQueryResult:
    """Graph response with truncation metadata."""

    graph: GiraffeGraph
    truncated: bool


_CACHE_TTL_SECONDS = 300.0
_query_cache: dict[tuple[str, int, str, int, int], tuple[float, GraphQueryResult]] = {}
_query_cache_lock = RLock()


def invalidate_neighborhood_cache() -> None:
    """Invalidate successful neighborhood results after graph writes."""
    with _query_cache_lock:
        _query_cache.clear()


def query_neighborhood(
    session: Session,
    seed: str,
    depth: int = 1,
    direction: str = "both",
    max_nodes: int = 200,
    max_edges: int = 500,
) -> GraphQueryResult:
    """Traverse an adjacency table with strict bounds and cycle protection."""
    if depth not in {1, 2, 3}:
        raise ValueError("depth must be between 1 and 3")
    if direction not in {"upstream", "downstream", "both"}:
        raise ValueError("invalid direction")
    normalized_seed = seed.upper()
    cache_key = (normalized_seed, depth, direction, max_nodes, max_edges)
    now = monotonic()
    with _query_cache_lock:
        cached = _query_cache.get(cache_key)
        if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]
        if cached is not None:
            _query_cache.pop(cache_key, None)
    visited = {normalized_seed}
    frontier = set(visited)
    edge_ids: set[str] = set()
    selected_edges: dict[str, SupplyChainEdge] = {}
    selected_nodes: dict[str, SupplyChainNode] = {}
    for _ in range(depth):
        next_frontier: set[str] = set()
        # 所有边约定 src=上游、dst=下游，与 edge_type 无关（边可能以任一端视角存储）。
        # 因此上游=任何 dst 在 frontier 的边，下游=任何 src 在 frontier 的边。
        src_node = aliased(SupplyChainNode)
        dst_node = aliased(SupplyChainNode)
        edge_query = select(SupplyChainEdge, src_node, dst_node).join(
            src_node, col(SupplyChainEdge.src_node_id) == col(src_node.node_id)
        ).join(
            dst_node, col(SupplyChainEdge.dst_node_id) == col(dst_node.node_id)
        ).order_by(
            col(SupplyChainEdge.confidence).desc(),
            col(SupplyChainEdge.updated_at).desc(),
        )
        per_direction_limit = min(20, max_edges)
        upstream_condition = col(SupplyChainEdge.dst_node_id).in_(frontier)
        downstream_condition = col(SupplyChainEdge.src_node_id).in_(frontier)
        condition = (
            upstream_condition
            if direction == "upstream"
            else downstream_condition
            if direction == "downstream"
            else or_(upstream_condition, downstream_condition)
        )
        candidate_limit = per_direction_limit if direction != "both" else per_direction_limit * 4
        candidates = session.exec(edge_query.where(condition).limit(candidate_limit))
        edges: dict[str, SupplyChainEdge] = {}
        upstream_count = 0
        downstream_count = 0
        for edge, source, destination in candidates:
            is_upstream = edge.dst_node_id in frontier
            is_downstream = edge.src_node_id in frontier
            if direction in {"upstream", "both"} and is_upstream and upstream_count < per_direction_limit:
                edges[edge.edge_id] = edge
                selected_nodes[source.node_id] = source
                selected_nodes[destination.node_id] = destination
                upstream_count += 1
            if direction in {"downstream", "both"} and is_downstream and downstream_count < per_direction_limit:
                edges[edge.edge_id] = edge
                selected_nodes[source.node_id] = source
                selected_nodes[destination.node_id] = destination
                downstream_count += 1
        for edge in edges.values():
            edge_ids.add(edge.edge_id)
            selected_edges[edge.edge_id] = edge
            next_frontier.update((edge.src_node_id, edge.dst_node_id))
        frontier = next_frontier - visited
        visited.update(frontier)
        if not frontier:
            break
    graph = GiraffeGraph(
        nodes=[
            GiraffeNode(
                node_id=node.node_id,
                node_type=node.node_type,
                properties=[
                    GiraffeProperty(name=name, value=value)
                    for name, value in {"name": node.name, **node.properties}.items()
                ],
            )
            for node in selected_nodes.values()
        ],
        edges=[
            GiraffeEdge(
                src_type=edge.src_type,
                src_id=edge.src_node_id,
                dst_type=edge.dst_type,
                dst_id=edge.dst_node_id,
                edge_type=edge.edge_type,
                timestamp=edge.timestamp,
                edge_id=edge.edge_id,
                properties=[
                    GiraffeProperty(name=name, value=value)
                    for name, value in {
                        **edge.properties,
                        "confidence": edge.confidence,
                        "confidence_source": edge.confidence_source,
                    }.items()
                ],
            )
            for edge in selected_edges.values()
        ],
    )
    truncated = len(graph.nodes) > max_nodes or len(graph.edges) > max_edges
    if truncated:
        seed_node = next((node for node in graph.nodes if str(node.node_id) == seed.upper()), GiraffeNode(node_id=seed.upper(), node_type="company"))
        graph.edges = [edge for edge in graph.edges if str(edge.edge_id) in edge_ids][:max_edges]
        graph = graph.page_rank(seed_node, top_n=max_nodes)
    result = GraphQueryResult(graph=graph, truncated=truncated)
    with _query_cache_lock:
        _query_cache[cache_key] = (monotonic(), result)
    return result
