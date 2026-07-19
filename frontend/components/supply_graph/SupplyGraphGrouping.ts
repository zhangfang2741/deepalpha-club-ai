import type { SupplyEdge, SupplyGraph, SupplyNode } from "@/lib/api/supplyGraph";

const LOW_CONFIDENCE_THRESHOLD = 60;
const MIN_GROUP_SIZE = 2;

const propertiesOf = (properties: { name: string; value: unknown }[]) =>
  Object.fromEntries(properties.map((property) => [property.name, property.value]));

const normalizedConfidence = (edge: SupplyEdge) => {
  const value = Number(propertiesOf(edge.properties).confidence || 0);
  return value > 0 && value <= 1 ? value * 100 : value;
};

const nodeLabel = (node: SupplyNode) => {
  const properties = propertiesOf(node.properties);
  return String(
    properties.ticker || properties.name_zh || properties.name || node.nodeId,
  );
};

const edgeProduct = (edge: SupplyEdge) => {
  const properties = propertiesOf(edge.properties);
  return String(properties.product_text || properties.product || "产品未披露");
};

const compactGroupLabel = (values: string[]) => {
  const unique = [...new Set(values.map((value) => value.trim()).filter(Boolean))];
  const visible = unique.slice(0, 3);
  return `${visible.join(" / ")}${unique.length > visible.length ? " / …" : ""}`;
};

export type GroupedRelationItem = {
  node: SupplyNode;
  edge: SupplyEdge;
};

export type GroupedRelation = {
  id: string;
  nodeId: string;
  edgeId: string;
  anchorId: string;
  kind: "supplier" | "customer";
  items: GroupedRelationItem[];
};

type Candidate = GroupedRelationItem & {
  anchorId: string;
  kind: GroupedRelation["kind"];
};

export const groupLowConfidenceRelations = (
  graph: SupplyGraph,
): {
  graph: SupplyGraph;
  groupsByElementId: Map<string, GroupedRelation>;
} => {
  const nodesById = new Map(graph.nodes.map((node) => [node.nodeId, node]));
  const degree = new Map<string, number>();
  graph.edges.forEach((edge) => {
    degree.set(edge.srcId, (degree.get(edge.srcId) || 0) + 1);
    degree.set(edge.dstId, (degree.get(edge.dstId) || 0) + 1);
  });

  const buckets = new Map<string, Candidate[]>();
  graph.edges.forEach((edge) => {
    const confidence = normalizedConfidence(edge);
    if (confidence <= 0 || confidence >= LOW_CONFIDENCE_THRESHOLD) return;
    const isSupplier = edge.edgeType === "SUPPLIED_BY";
    const anchorId = isSupplier ? edge.dstId : edge.srcId;
    const peripheralId = isSupplier ? edge.srcId : edge.dstId;
    const node = nodesById.get(peripheralId);
    if (!node || degree.get(peripheralId) !== 1) return;
    const kind: GroupedRelation["kind"] = isSupplier ? "supplier" : "customer";
    const key = `${kind}:${anchorId}`;
    const candidates = buckets.get(key) || [];
    candidates.push({ node, edge, anchorId, kind });
    buckets.set(key, candidates);
  });

  const collapsedNodeIds = new Set<string>();
  const collapsedEdgeIds = new Set<string>();
  const groupedNodes: SupplyNode[] = [];
  const groupedEdges: SupplyEdge[] = [];
  const groupsByElementId = new Map<string, GroupedRelation>();

  for (const [key, candidates] of buckets) {
    if (candidates.length < MIN_GROUP_SIZE) continue;
    const { anchorId, kind } = candidates[0];
    const safeKey = key.replace(/[^a-zA-Z0-9_-]/g, "_");
    const nodeId = `__low_confidence_group_node__${safeKey}`;
    const edgeId = `__low_confidence_group_edge__${safeKey}`;
    const items = candidates.map(({ node, edge }) => ({ node, edge }));
    const group: GroupedRelation = {
      id: safeKey,
      nodeId,
      edgeId,
      anchorId,
      kind,
      items,
    };
    const count = items.length;
    const companySummary = compactGroupLabel(items.map(({ node }) => nodeLabel(node)));
    const productSummary = compactGroupLabel(items.map(({ edge }) => edgeProduct(edge)));
    const label = kind === "supplier" ? "低置信度供应商" : "低置信度客户";

    items.forEach(({ node, edge }) => {
      collapsedNodeIds.add(node.nodeId);
      collapsedEdgeIds.add(edge.edgeId);
    });
    groupedNodes.push({
      nodeId,
      nodeType: `${kind}_group`,
      properties: [
        { name: "name", value: `${label} × ${count}` },
        { name: "name_zh", value: `${label} × ${count}` },
        { name: "is_grouped", value: true },
        { name: "group_count", value: count },
        { name: "group_kind", value: kind },
      ],
    });
    groupedEdges.push({
      edgeId,
      srcId: kind === "supplier" ? nodeId : anchorId,
      dstId: kind === "supplier" ? anchorId : nodeId,
      edgeType: kind === "supplier" ? "SUPPLIED_BY" : "CUSTOMER_OF",
      properties: [
        { name: "product", value: productSummary },
        { name: "group_label", value: companySummary },
        { name: "is_grouped", value: true },
        { name: "group_count", value: count },
        { name: "confidence", value: LOW_CONFIDENCE_THRESHOLD - 1 },
      ],
    });
    groupsByElementId.set(nodeId, group);
    groupsByElementId.set(edgeId, group);
  }

  return {
    graph: {
      ...graph,
      nodes: [
        ...graph.nodes.filter((node) => !collapsedNodeIds.has(node.nodeId)),
        ...groupedNodes,
      ],
      edges: [
        ...graph.edges.filter((edge) => !collapsedEdgeIds.has(edge.edgeId)),
        ...groupedEdges,
      ],
    },
    groupsByElementId,
  };
};
