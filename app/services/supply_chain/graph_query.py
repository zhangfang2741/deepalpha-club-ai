"""Bounded multi-hop graph queries."""

from dataclasses import dataclass

from sqlalchemy import and_, or_
from sqlmodel import Session, col, select

from app.models.supply_chain_edge import SupplyChainEdge
from app.services.supply_chain.domain import GiraffeGraph, GiraffeNode
from app.services.supply_chain.repository import SupplyChainRepository


@dataclass(frozen=True)
class GraphQueryResult:
    """Graph response with truncation metadata."""

    graph: GiraffeGraph
    truncated: bool


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
    visited = {seed.upper()}
    frontier = set(visited)
    edge_ids: set[str] = set()
    for _ in range(depth):
        next_frontier: set[str] = set()
        if direction == "upstream":
            condition = and_(col(SupplyChainEdge.edge_type) == "SUPPLIED_BY", col(SupplyChainEdge.dst_node_id).in_(frontier))
        elif direction == "downstream":
            condition = and_(col(SupplyChainEdge.edge_type) == "CUSTOMER_OF", col(SupplyChainEdge.src_node_id).in_(frontier))
        else:
            condition = or_(col(SupplyChainEdge.src_node_id).in_(frontier), col(SupplyChainEdge.dst_node_id).in_(frontier))
        latest = session.exec(
            select(SupplyChainEdge).where(condition).order_by(col(SupplyChainEdge.updated_at).desc()).limit(1)
        ).first()
        if latest is not None and latest.last_run_id is not None:
            condition = and_(condition, col(SupplyChainEdge.last_run_id) == latest.last_run_id)
        for edge in session.exec(select(SupplyChainEdge).where(condition)):
            edge_ids.add(edge.edge_id)
            next_frontier.update((edge.src_node_id, edge.dst_node_id))
        frontier = next_frontier - visited
        visited.update(frontier)
        if not frontier:
            break
    graph = SupplyChainRepository(session).load_graph(visited, edge_ids)
    truncated = len(graph.nodes) > max_nodes or len(graph.edges) > max_edges
    if truncated:
        seed_node = next((node for node in graph.nodes if str(node.node_id) == seed.upper()), GiraffeNode(node_id=seed.upper(), node_type="company"))
        graph.edges = [edge for edge in graph.edges if str(edge.edge_id) in edge_ids][:max_edges]
        graph = graph.page_rank(seed_node, top_n=max_nodes)
    return GraphQueryResult(graph=graph, truncated=truncated)
