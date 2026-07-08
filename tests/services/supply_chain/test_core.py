"""Core supply-chain domain tests."""

from app.services.supply_chain.alias_resolver import normalize_alias
from app.services.supply_chain.domain import GiraffeEdge, GiraffeGraph, GiraffeNode, GiraffeProperty
from app.services.supply_chain.fmp_universe import FMPUniverse, ListedCompany
from app.services.supply_chain.product_taxonomy import normalize_product


def props(**values: object) -> list[GiraffeProperty]:
    """Build graph properties."""
    return [GiraffeProperty(name=name, value=value) for name, value in values.items()]


def test_alias_and_taxonomy_normalize() -> None:
    """Common aliases and products map deterministically."""
    assert normalize_alias("Foxconn") == "Hon Hai Precision Industry"
    assert normalize_alias("富士康") == "Hon Hai Precision Industry"
    assert normalize_product("HBM high bandwidth memory") == "hbm"
    assert normalize_product("EUV lithography equipment") == "lithography"


def test_universe_matching() -> None:
    """Universe supports ticker, alias, and conservative fuzzy matching."""
    universe = FMPUniverse(
        [ListedCompany("TSM", "Taiwan Semiconductor Manufacturing"), ListedCompany("NVDA", "NVIDIA Corporation")]
    )
    assert universe.match("TSM").symbol == "TSM"
    assert universe.match("TSMC").symbol == "TSM"
    assert universe.match("NVIDIA Corporatio").symbol == "NVDA"
    assert universe.match("Unknown Widgets") is None


def test_universe_matching_ignores_model_qualifiers_and_company_suffixes() -> None:
    """Model display qualifiers still resolve to listed-company symbols."""
    universe = FMPUniverse(
        [
            ListedCompany("META", "Meta Platforms, Inc."),
            ListedCompany("GOOGL", "Alphabet Inc."),
            ListedCompany("AMZN", "Amazon.com, Inc."),
            ListedCompany("MSFT", "Microsoft Corporation"),
            ListedCompany("HPE", "Hewlett Packard Enterprise Company"),
        ]
    )
    assert universe.match("Meta Platforms").symbol == "META"
    assert universe.match("Alphabet (Google)").symbol == "GOOGL"
    assert universe.match("Amazon (AWS)").symbol == "AMZN"
    assert universe.match("Microsoft").symbol == "MSFT"
    assert universe.match("Hewlett Packard Enterprise (HPE)").symbol == "HPE"


def test_edge_id_ignores_timestamp_and_graph_algorithms() -> None:
    """Mutable timestamps do not change identity and traversal is bounded."""
    first = GiraffeEdge(
        src_type="supplier",
        src_id="TSM",
        dst_type="company",
        dst_id="NVDA",
        edge_type="SUPPLIED_BY",
        timestamp=1,
        properties=props(product_category="wafer_foundry", confidence=80),
    )
    second = first.model_copy(update={"timestamp": 999, "edge_id": None})
    second.edge_id = second.generate_edge_id()
    assert first.edge_id == second.edge_id
    graph = GiraffeGraph(
        nodes=[GiraffeNode(node_id="TSM", node_type="supplier"), GiraffeNode(node_id="NVDA", node_type="company")],
        edges=[first],
    )
    assert len(graph.sub_graph([GiraffeNode(node_id="NVDA", node_type="company")], max_depth=1).edges) == 1
    assert graph.to_dict()["edges"][0]["srcId"] == "TSM"
