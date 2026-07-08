"""Lightweight property graph adapted from giraffeai.

Changes from upstream: local deterministic UUIDs, no transformers/internal
logger dependency, supply-chain property whitelist, confidence-first trimming,
and edge identity excludes mutable timestamps.
"""

from __future__ import annotations

from collections import deque
from typing import Any, ClassVar

import networkx as nx
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.utils.uuid_util import generate_uuid_from_str


class GiraffeDomain(BaseModel):
    """Base domain model with camel-case serialization."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class GiraffeProperty(GiraffeDomain):
    """A named property."""

    name: str
    value: Any = None

    def __hash__(self) -> int:
        return hash((self.name, str(self.value)))


class GiraffeNode(GiraffeDomain):
    """Property graph node."""

    node_id: str | int
    node_type: str
    properties: list[GiraffeProperty] = Field(default_factory=list)

    def __hash__(self) -> int:
        return hash((self.node_type, self.node_id))

    def get_property(self, name: str, default: Any = None) -> Any:
        return next((prop.value for prop in self.properties if prop.name == name), default)

    def get_properties(self) -> dict[str, Any]:
        return {prop.name: prop.value for prop in self.properties}


class GiraffeEdge(GiraffeDomain):
    """Directed property graph edge."""

    src_type: str
    src_id: str | int
    dst_type: str
    dst_id: str | int
    edge_type: str
    timestamp: int | None = None
    edge_id: str | int | None = None
    properties: list[GiraffeProperty] = Field(default_factory=list)

    def model_post_init(self, _: Any) -> None:
        if self.edge_id is None:
            self.edge_id = self.generate_edge_id()

    def __hash__(self) -> int:
        return hash(str(self.edge_id))

    def get_property(self, name: str, default: Any = None) -> Any:
        return next((prop.value for prop in self.properties if prop.name == name), default)

    def get_properties(self) -> dict[str, Any]:
        return {prop.name: prop.value for prop in self.properties}

    def add_property(self, name: str, value: Any) -> GiraffeEdge:
        for prop in self.properties:
            if prop.name == name:
                prop.value = value
                return self
        self.properties.append(GiraffeProperty(name=name, value=value))
        return self

    def generate_edge_id(self) -> str:
        category = self.get_property("product_category", "other")
        key = "|".join(map(str, (self.src_id, self.dst_id, self.edge_type, category)))
        return generate_uuid_from_str(key)


class GiraffeGraph(GiraffeDomain):
    """Graph container and compact analysis helpers."""

    KEY_PROPERTIES: ClassVar[set[str]] = {
        "confidence", "confidence_source", "product", "product_category",
        "is_single_source", "ticker", "is_listed", "expandable",
    }
    graph_id: str | int | None = None
    edges: list[GiraffeEdge] = Field(default_factory=list)
    nodes: list[GiraffeNode] = Field(default_factory=list)

    def alignment(self) -> GiraffeGraph:
        known = {(node.node_type, node.node_id): node for node in self.nodes}
        for edge in self.edges:
            known.setdefault((edge.src_type, edge.src_id), GiraffeNode(node_id=edge.src_id, node_type=edge.src_type))
            known.setdefault((edge.dst_type, edge.dst_id), GiraffeNode(node_id=edge.dst_id, node_type=edge.dst_type))
        self.nodes = list(known.values())
        self.edges = list({str(edge.edge_id): edge for edge in self.edges}.values())
        return self

    def sub_graph(self, seed_nodes: list[GiraffeNode] | None = None, max_depth: int | None = None) -> GiraffeGraph:
        seeds = seed_nodes or []
        adjacency: dict[tuple[str, str | int], list[GiraffeEdge]] = {}
        for edge in self.edges:
            adjacency.setdefault((edge.src_type, edge.src_id), []).append(edge)
            adjacency.setdefault((edge.dst_type, edge.dst_id), []).append(edge)
        queue = deque(((node.node_type, node.node_id), 0) for node in seeds)
        visited = {key for key, _ in queue}
        selected: dict[str, GiraffeEdge] = {}
        while queue:
            key, depth = queue.popleft()
            if max_depth is not None and depth >= max_depth:
                continue
            for edge in adjacency.get(key, []):
                selected[str(edge.edge_id)] = edge
                other = (edge.dst_type, edge.dst_id) if key == (edge.src_type, edge.src_id) else (edge.src_type, edge.src_id)
                if other not in visited:
                    visited.add(other)
                    queue.append((other, depth + 1))
        nodes = [node for node in self.nodes if (node.node_type, node.node_id) in visited]
        return GiraffeGraph(graph_id=self.graph_id, nodes=nodes, edges=list(selected.values()))

    def page_rank(self, seed_node: GiraffeNode, top_n: int = 200) -> GiraffeGraph:
        graph = nx.DiGraph()
        for edge in self.edges:
            graph.add_edge(str(edge.src_id), str(edge.dst_id), weight=max(int(edge.get_property("confidence", 1)), 1))
        if not graph:
            return self
        personalization = {node: 0.0 for node in graph.nodes}
        if str(seed_node.node_id) in personalization:
            personalization[str(seed_node.node_id)] = 1.0
        scores = nx.pagerank(graph, personalization=personalization or None, weight="weight")
        keep = {node for node, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_n]}
        nodes = [node for node in self.nodes if str(node.node_id) in keep]
        edges = [edge for edge in self.edges if str(edge.src_id) in keep and str(edge.dst_id) in keep]
        return GiraffeGraph(graph_id=self.graph_id, nodes=nodes, edges=edges)

    def diff(self, other: GiraffeGraph) -> GiraffeGraph:
        old = {str(edge.edge_id): edge for edge in other.edges}
        changed = []
        for edge in self.edges:
            previous = old.get(str(edge.edge_id))
            if previous is None or abs(int(edge.get_property("confidence", 0)) - int(previous.get_property("confidence", 0))) >= 20:
                changed.append(edge.model_copy(deep=True).add_property("changed", True))
        return GiraffeGraph(nodes=self.nodes, edges=changed).alignment()

    def trim_to_token_limit(self, max_tokens: int = 4000) -> GiraffeGraph:
        def estimate() -> int:
            return len(str(self.to_dict())) // 4

        self.edges.sort(key=lambda edge: int(edge.get_property("confidence", 0)))
        while self.edges and estimate() > max_tokens:
            self.edges.pop(0)
        connected = {str(value) for edge in self.edges for value in (edge.src_id, edge.dst_id)}
        self.nodes = [node for node in self.nodes if str(node.node_id) in connected]
        return self

    def flat_nodes(self) -> pd.DataFrame:
        return pd.DataFrame([{"node_id": node.node_id, "node_type": node.node_type, **node.get_properties()} for node in self.nodes])

    def flat_edges(self) -> pd.DataFrame:
        return pd.DataFrame([{"edge_id": edge.edge_id, "src_id": edge.src_id, "dst_id": edge.dst_id, **edge.get_properties()} for edge in self.edges])

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)
