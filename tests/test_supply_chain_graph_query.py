"""Tests for bounded supply-chain neighborhood queries."""

import uuid

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models.supply_chain_edge import SupplyChainEdge
from app.models.supply_chain_node import SupplyChainNode
from app.services.supply_chain.discover import DiscoveryResult, SupplyRelation
from app.services.supply_chain.graph_query import invalidate_neighborhood_cache, query_neighborhood
from app.services.supply_chain.realtime import build_realtime_graph


def test_neighborhood_combines_relationships_from_different_runs() -> None:
    """A newer run must not hide valid relationships produced by older runs."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    invalidate_neighborhood_cache()
    SQLModel.metadata.create_all(engine)
    older_run_id = uuid.uuid4()
    newer_run_id = uuid.uuid4()

    with Session(engine) as session:
        session.add_all(
            [
                SupplyChainNode(node_id="TSM", node_type="company", name="TSMC"),
                SupplyChainNode(node_id="NVDA", node_type="company", name="NVIDIA"),
                SupplyChainNode(node_id="META", node_type="company", name="Meta"),
                SupplyChainEdge(
                    edge_id="tsm-nvda",
                    src_node_id="TSM",
                    src_type="company",
                    dst_node_id="NVDA",
                    dst_type="company",
                    edge_type="SUPPLIED_BY",
                    timestamp=1,
                    confidence=90,
                    last_run_id=older_run_id,
                ),
                SupplyChainEdge(
                    edge_id="nvda-meta",
                    src_node_id="NVDA",
                    src_type="company",
                    dst_node_id="META",
                    dst_type="company",
                    edge_type="CUSTOMER_OF",
                    timestamp=2,
                    confidence=92,
                    last_run_id=newer_run_id,
                ),
            ]
        )
        session.commit()

        result = query_neighborhood(session, "NVDA", depth=1, direction="both")

    assert {str(edge.edge_id) for edge in result.graph.edges} == {"tsm-nvda", "nvda-meta"}
    assert {str(node.node_id) for node in result.graph.nodes} == {"TSM", "NVDA", "META"}


def test_neighborhood_limits_each_direction_to_core_relationships() -> None:
    """Large histories stay bounded without allowing one direction to crowd out the other."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    invalidate_neighborhood_cache()
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(SupplyChainNode(node_id="NVDA", node_type="company", name="NVIDIA"))
        for index in range(25):
            supplier = f"SUP{index}"
            customer = f"CUS{index}"
            session.add_all(
                [
                    SupplyChainNode(node_id=supplier, node_type="company", name=supplier),
                    SupplyChainNode(node_id=customer, node_type="company", name=customer),
                    SupplyChainEdge(
                        edge_id=f"{supplier}-nvda",
                        src_node_id=supplier,
                        src_type="company",
                        dst_node_id="NVDA",
                        dst_type="company",
                        edge_type="SUPPLIED_BY",
                        timestamp=index,
                        confidence=index,
                    ),
                    SupplyChainEdge(
                        edge_id=f"nvda-{customer}",
                        src_node_id="NVDA",
                        src_type="company",
                        dst_node_id=customer,
                        dst_type="company",
                        edge_type="CUSTOMER_OF",
                        timestamp=index,
                        confidence=index,
                    ),
                ]
            )
        session.commit()

        result = query_neighborhood(session, "NVDA", depth=1, direction="both")

    assert len(result.graph.edges) == 40
    assert sum(str(edge.dst_id) == "NVDA" for edge in result.graph.edges) == 20
    assert sum(str(edge.src_id) == "NVDA" for edge in result.graph.edges) == 20


def test_realtime_graph_uses_ticker_as_unique_node_identity() -> None:
    """Different company names with the same ticker render as one node."""
    result = DiscoveryResult(
        company_name_zh="英伟达",
        suppliers=[
            SupplyRelation(
                supplier_name="Taiwan Semiconductor Manufacturing",
                supplier_ticker="tsm",
                product_text="advanced foundry",
                confidence=95,
            ),
            SupplyRelation(
                supplier_name="TSMC",
                supplier_ticker="TSM",
                product_text="CoWoS packaging",
                confidence=94,
            ),
        ],
    )

    graph = build_realtime_graph("nvda", result)

    assert [str(node.node_id) for node in graph.nodes].count("TSM") == 1
    assert {str(node.node_id) for node in graph.nodes} == {"NVDA", "TSM"}
