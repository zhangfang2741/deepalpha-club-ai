"""Verification candidate selection."""

from sqlmodel import Session, select

from app.core.config import settings
from app.models.supply_chain_edge import SupplyChainEdge
from app.models.supply_chain_node import SupplyChainNode
from app.services.supply_chain.domain import GiraffeEdge, GiraffeProperty


def select_edges_to_verify(ticker: str, session: Session, threshold: int | None = None) -> list[GiraffeEdge]:
    """Select LLM edges matching any risk trigger."""
    threshold = threshold if threshold is not None else settings.SUPPLY_CHAIN_VERIFY_THRESHOLD
    buyer = session.exec(select(SupplyChainNode).where(SupplyChainNode.node_id == ticker.upper())).first()
    market_cap = float((buyer.properties if buyer else {}).get("market_cap") or 0)
    small_cap = bool(market_cap and market_cap < settings.SUPPLY_CHAIN_SMALLCAP_MARKETCAP)
    rows = session.exec(
        select(SupplyChainEdge).where(
            SupplyChainEdge.dst_node_id == ticker.upper(),
            SupplyChainEdge.confidence_source == "LLM",
        )
    ).all()
    generic = {item.lower() for item in settings.SUPPLY_CHAIN_GENERIC_SUPPLIERS}
    selected = []
    for row in rows:
        supplier = session.exec(select(SupplyChainNode).where(SupplyChainNode.node_id == row.src_node_id)).first()
        is_generic = bool(supplier and ({supplier.name.lower(), str(supplier.properties.get("ticker", "")).lower()} & generic))
        if row.confidence < threshold or is_generic or small_cap or bool(row.properties.get("is_single_source")):
            selected.append(GiraffeEdge(src_type=row.src_type, src_id=row.src_node_id, dst_type=row.dst_type, dst_id=row.dst_node_id, edge_type=row.edge_type, timestamp=row.timestamp, edge_id=row.edge_id, properties=[GiraffeProperty(name=name, value=value) for name, value in {**row.properties, "confidence": row.confidence, "confidence_source": row.confidence_source}.items()]))
    return selected
