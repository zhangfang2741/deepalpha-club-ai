"""SQLModel ↔ property graph persistence mapping."""

import uuid
from datetime import UTC, datetime

from sqlmodel import Session, col, select

from app.models.supply_chain_edge import SupplyChainEdge
from app.models.supply_chain_node import SupplyChainNode
from app.services.supply_chain.domain import GiraffeEdge, GiraffeGraph, GiraffeNode, GiraffeProperty
from app.services.supply_chain.graph_query import invalidate_neighborhood_cache


def _properties(value: dict) -> list[GiraffeProperty]:
    return [GiraffeProperty(name=name, value=item) for name, item in value.items()]


class SupplyChainRepository:
    """Persistence boundary for supply-chain graphs."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_graph(self, graph: GiraffeGraph, run_id: uuid.UUID | None = None) -> None:
        """Idempotently upsert nodes and edges by business key."""
        now = datetime.now(UTC)
        for node in graph.nodes:
            row = self.session.exec(select(SupplyChainNode).where(SupplyChainNode.node_id == str(node.node_id))).first()
            props = node.get_properties()
            if row is None:
                row = SupplyChainNode(node_id=str(node.node_id), node_type=node.node_type, name=str(props.get("name") or node.node_id), properties=props, first_seen_run_id=run_id)
                self.session.add(row)
            else:
                row.node_type, row.name, row.properties, row.updated_at = node.node_type, str(props.get("name") or row.name), props, now
        for edge in graph.edges:
            edge_id = str(edge.edge_id or edge.generate_edge_id())
            row = self.session.exec(select(SupplyChainEdge).where(SupplyChainEdge.edge_id == edge_id)).first()
            props = edge.get_properties()
            values = dict(src_node_id=str(edge.src_id), src_type=edge.src_type, dst_node_id=str(edge.dst_id), dst_type=edge.dst_type, edge_type=edge.edge_type, timestamp=int(edge.timestamp or now.timestamp()), properties=props, confidence=int(props.get("confidence", 0)), confidence_source=str(props.get("confidence_source", "LLM")), last_run_id=run_id)
            if row is None:
                row = SupplyChainEdge(
                    edge_id=edge_id, src_node_id=str(edge.src_id), src_type=edge.src_type,
                    dst_node_id=str(edge.dst_id), dst_type=edge.dst_type, edge_type=edge.edge_type,
                    timestamp=int(edge.timestamp or now.timestamp()), properties=props,
                    confidence=int(props.get("confidence", 0)),
                    confidence_source=str(props.get("confidence_source", "LLM")), last_run_id=run_id,
                )
                self.session.add(row)
            else:
                for name, value in values.items():
                    setattr(row, name, value)
                row.updated_at = now
        self.session.commit()
        invalidate_neighborhood_cache()

    def load_graph(self, node_ids: set[str] | None = None, edge_ids: set[str] | None = None) -> GiraffeGraph:
        """Load the full graph or a node-filtered slice."""
        node_query = select(SupplyChainNode)
        edge_query = select(SupplyChainEdge)
        if node_ids is not None:
            node_query = node_query.where(col(SupplyChainNode.node_id).in_(node_ids))
            edge_query = edge_query.where(
                col(SupplyChainEdge.src_node_id).in_(node_ids),
                col(SupplyChainEdge.dst_node_id).in_(node_ids),
            )
        if edge_ids is not None:
            edge_query = edge_query.where(col(SupplyChainEdge.edge_id).in_(edge_ids))
        nodes = list(self.session.exec(node_query))
        edges = list(self.session.exec(edge_query))
        return GiraffeGraph(
            nodes=[GiraffeNode(node_id=node.node_id, node_type=node.node_type, properties=_properties({"name": node.name, **node.properties})) for node in nodes],
            edges=[GiraffeEdge(src_type=edge.src_type, src_id=edge.src_node_id, dst_type=edge.dst_type, dst_id=edge.dst_node_id, edge_type=edge.edge_type, timestamp=edge.timestamp, edge_id=edge.edge_id, properties=_properties({**edge.properties, "confidence": edge.confidence, "confidence_source": edge.confidence_source})) for edge in edges],
        )
