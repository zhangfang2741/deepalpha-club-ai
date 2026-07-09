import type {
  SupplyEdge,
  SupplyGraph,
  SupplyNode,
} from "@/lib/api/supplyGraph";

const props = (items: { name: string; value: unknown }[]) =>
  Object.fromEntries(items.map((item) => [item.name, item.value]));

const compactProduct = (value: string) => {
  const known = value.match(
    /\b(HBM\d*[A-Z]?|EUV|LFP|NMC\d*|GPU|CPU|CoWoS|DDR\d?|GDDR\d?|LiOH|SiC|GaN)\b/gi,
  );
  if (known?.length)
    return [...new Set(known.map((item) => item.toUpperCase()))].join(" / ");
  const first = value.split(/[、,，;/]/)[0]?.trim() || "产品";
  return first.length > 16 ? `${first.slice(0, 15)}…` : first;
};

const US_TICKER = /^[A-Z]{1,5}(?:[.-][A-Z]{1,2})?$/;
const HOME_ICON = "/fa-home.svg";

export type G6Node = {
  id: string;
  type: string;
  data: Record<string, unknown>;
  style: Record<string, unknown>;
};
export type G6Edge = {
  id: string;
  type: string;
  source: string;
  target: string;
  data: Record<string, unknown>;
  style: Record<string, unknown>;
};
export type G6Data = { nodes: G6Node[]; edges: G6Edge[] };

export type NodeRole = "focus" | "supplier" | "customer" | "unknown";

// 相对焦点节点计算每个节点的角色：所有边约定 src=上游、dst=下游，
// 因此从焦点沿「入边」回溯到的是它的供应商（上游），沿「出边」到达的是它的客户（下游）。
// 这样即便某条边以对方视角存储（如 TER→NVDA 记为「NVDA 是 TER 的客户」），
// 在以 NVDA 为焦点的图里 TER 仍正确显示为 NVDA 的供应商。
export const computeNodeRoles = (
  graph: SupplyGraph,
  focusId?: string,
): Map<string, NodeRole> => {
  const roles = new Map<string, NodeRole>();
  if (!focusId) {
    graph.nodes.forEach((node) => roles.set(node.nodeId, "unknown"));
    return roles;
  }
  const incoming = new Map<string, string[]>();
  const outgoing = new Map<string, string[]>();
  graph.edges.forEach((edge) => {
    if (!incoming.has(edge.dstId)) incoming.set(edge.dstId, []);
    incoming.get(edge.dstId)!.push(edge.srcId);
    if (!outgoing.has(edge.srcId)) outgoing.set(edge.srcId, []);
    outgoing.get(edge.srcId)!.push(edge.dstId);
  });
  const walk = (adjacency: Map<string, string[]>) => {
    const reached = new Set<string>();
    const stack = [focusId];
    const seen = new Set([focusId]);
    while (stack.length) {
      const current = stack.pop()!;
      for (const next of adjacency.get(current) ?? []) {
        if (seen.has(next)) continue;
        seen.add(next);
        reached.add(next);
        stack.push(next);
      }
    }
    return reached;
  };
  const supplierSide = walk(incoming);
  const customerSide = walk(outgoing);
  graph.nodes.forEach((node) => {
    if (node.nodeId === focusId) roles.set(node.nodeId, "focus");
    else if (supplierSide.has(node.nodeId)) roles.set(node.nodeId, "supplier");
    else if (customerSide.has(node.nodeId)) roles.set(node.nodeId, "customer");
    else roles.set(node.nodeId, "unknown");
  });
  return roles;
};

// 边相对焦点属于「供应链（流向焦点）」还是「客户链（离开焦点）」。
export const resolveEdgeRole = (
  edge: SupplyEdge,
  roles: Map<string, NodeRole>,
  focusId?: string,
): "supply" | "customer" => {
  if (edge.dstId === focusId || roles.get(edge.dstId) === "supplier")
    return "supply";
  if (edge.srcId === focusId || roles.get(edge.srcId) === "customer")
    return "customer";
  return edge.edgeType === "SUPPLIED_BY" ? "supply" : "customer";
};

const ROLE_STROKE: Record<NodeRole, string> = {
  focus: "#f5a623",
  supplier: "#4f8df7",
  customer: "#22b983",
  unknown: "#94a3b8",
};

const nodeToG6 = (node: SupplyNode, role: NodeRole): G6Node => {
  const isFocus = role === "focus";
  const data = props(node.properties);
  const name = String(data.name || node.nodeId);
  const nameZh = data.name_zh ? String(data.name_zh) : "";
  const propertyTicker = data.ticker
    ? String(data.ticker).trim().toUpperCase()
    : "";
  const nodeIdTicker = String(node.nodeId).trim().toUpperCase();
  const ticker = US_TICKER.test(propertyTicker)
    ? propertyTicker
    : US_TICKER.test(nodeIdTicker)
      ? nodeIdTicker
      : "";
  const label = nameZh || name;
  return {
    id: String(node.nodeId),
    type: "circle",
    data: { ...data, nodeType: node.nodeType },
    style: {
      cursor: "pointer",
      labelText: label,
      labelFill: "#27364f",
      labelFontSize: 12,
      labelFontWeight: 600,
      labelLineHeight: 16,
      labelPlacement: "bottom",
      labelOffsetY: 12,
      fill: isFocus ? "#fff4d6" : "#f7faff",
      stroke: ROLE_STROKE[role],
      lineWidth: isFocus ? 4 : 3,
      size: isFocus ? 72 : 54,
      iconSrc: ticker ? undefined : HOME_ICON,
      iconText: ticker || undefined,
      iconFill: "#4773b9",
      iconFontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
      iconFontWeight: 700,
      iconFontSize: ticker
        ? ticker.length >= 5
          ? isFocus
            ? 14
            : 10
          : isFocus
            ? 18
            : 13
        : undefined,
      iconWidth: isFocus ? 28 : 20,
      iconHeight: isFocus ? 28 : 20,
    },
  };
};

const edgeToG6 = (edge: SupplyEdge, role: "supply" | "customer"): G6Edge => {
  const data = props(edge.properties);
  const confidence = Number(data.confidence || 0);
  const product = compactProduct(
    String(data.product || data.product_text || "产品未披露"),
  );
  return {
    id: String(edge.edgeId),
    type: "quadratic",
    source: String(edge.srcId),
    target: String(edge.dstId),
    data: { ...data, edgeType: edge.edgeType },
    style: {
      labelText: `${product}\n置信度 ${confidence}%`,
      labelFill: "#334155",
      labelFontSize: 11,
      labelLineHeight: 15,
      labelBackground: true,
      labelBackgroundFill: "#ffffff",
      labelBackgroundOpacity: 0.9,
      labelBackgroundRadius: 6,
      labelPadding: [5, 8],
      stroke: role === "supply" ? "#66b7f0" : "#65cf98",
      strokeOpacity: 0.85,
      lineWidth: confidence >= 80 ? 2.5 : 2,
      endArrow: true,
      endArrowSize: 8,
      curveOffset: 18,
    },
  };
};

export const adaptGraph = (
  graph: SupplyGraph,
  preferredFocusId?: string,
): G6Data => {
  const degree = new Map<string, number>();
  graph.edges.forEach((edge) => {
    degree.set(edge.srcId, (degree.get(edge.srcId) || 0) + 1);
    degree.set(edge.dstId, (degree.get(edge.dstId) || 0) + 1);
  });
  const focusId =
    preferredFocusId ||
    [...degree.entries()].sort((left, right) => right[1] - left[1])[0]?.[0];
  const roles = computeNodeRoles(graph, focusId);
  return {
    nodes: graph.nodes.map((node) =>
      nodeToG6(node, roles.get(node.nodeId) ?? "unknown"),
    ),
    edges: graph.edges.map((edge) =>
      edgeToG6(edge, resolveEdgeRole(edge, roles, focusId)),
    ),
  };
};

export const mergeGraphs = (
  current: SupplyGraph,
  incoming: SupplyGraph,
): SupplyGraph => {
  const nodes = new Map(current.nodes.map((node) => [node.nodeId, node]));
  const edges = new Map(current.edges.map((edge) => [edge.edgeId, edge]));
  incoming.nodes.forEach((node) => nodes.set(node.nodeId, node));
  incoming.edges.forEach((edge) => edges.set(edge.edgeId, edge));
  return {
    nodes: [...nodes.values()],
    edges: [...edges.values()],
    truncated: current.truncated || incoming.truncated,
  };
};
