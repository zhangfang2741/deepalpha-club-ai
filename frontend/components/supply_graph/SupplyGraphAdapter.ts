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

const nodeToG6 = (node: SupplyNode, isFocus: boolean): G6Node => {
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
      stroke: isFocus
        ? "#f5a623"
        : node.nodeType === "supplier"
          ? "#4f8df7"
          : "#22b983",
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

const edgeToG6 = (edge: SupplyEdge): G6Edge => {
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
      stroke: edge.edgeType === "SUPPLIED_BY" ? "#66b7f0" : "#65cf98",
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
  return {
    nodes: graph.nodes.map((node) => nodeToG6(node, node.nodeId === focusId)),
    edges: graph.edges.map(edgeToG6),
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
