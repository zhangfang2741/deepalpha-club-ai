"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { SupplyGraph } from "@/lib/api/supplyGraph";
import { adaptGraph } from "./SupplyGraphAdapter";

type Direction = "upstream" | "downstream" | "both";
type ContextMenu = { nodeId: string; x: number; y: number } | null;
type LegendKey = "suppliers" | "customers" | "supplierEdges" | "customerEdges";
type LegendVisibility = Record<LegendKey, boolean>;
type ViewportState = { position: [number, number]; zoom: number };
type G6GraphInstance = {
  destroy: () => void;
  draw: () => Promise<void>;
  getPosition: () => number[];
  getZoom: () => number;
  on: (event: string, handler: (event: unknown) => void) => void;
  render: () => Promise<void>;
  translateTo: (position: [number, number], animation?: boolean) => Promise<void>;
  zoomTo: (zoom: number, animation?: boolean) => Promise<void>;
};

type GraphElementEvent = {
  target: { id: string };
  preventDefault?: () => void;
  stopPropagation?: () => void;
};

const LEGEND_ITEMS: {
  key: LegendKey;
  label: string;
  color: string;
  kind: "node" | "edge";
}[] = [
  { key: "suppliers", label: "供应商节点", color: "#4f8df7", kind: "node" },
  { key: "customers", label: "客户节点", color: "#22b983", kind: "node" },
  { key: "supplierEdges", label: "供应关系", color: "#66b7f0", kind: "edge" },
  { key: "customerEdges", label: "客户关系", color: "#65cf98", kind: "edge" },
];

const INITIAL_VISIBILITY: LegendVisibility = {
  suppliers: true,
  customers: true,
  supplierEdges: true,
  customerEdges: true,
};
const NODE_CLICK_CONFIRM_DELAY_MS = 320;

export default function SupplyGraphCanvas({
  graph,
  onNode,
  onEdge,
  onExpand,
  onNodeDoubleClick,
}: {
  graph: SupplyGraph;
  onNode: (id: string) => void;
  onEdge: (id: string) => void;
  onExpand: (id: string, direction: Direction) => void;
  onNodeDoubleClick: (id: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewportStateRef = useRef<ViewportState | null>(null);
  const renderedDataKeyRef = useRef<string>("");
  const clickTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [contextMenu, setContextMenu] = useState<ContextMenu>(null);
  const [visibility, setVisibility] =
    useState<LegendVisibility>(INITIAL_VISIBILITY);

  const graphDataKey = useMemo(
    () =>
      [
        graph.nodes.map((node) => node.nodeId).sort().join("|"),
        graph.edges.map((edge) => edge.edgeId).sort().join("|"),
      ].join("::"),
    [graph],
  );

  const { visibleGraph, focusId } = useMemo(() => {
    const degree = new Map<string, number>();
    graph.edges.forEach((edge) => {
      degree.set(edge.srcId, (degree.get(edge.srcId) || 0) + 1);
      degree.set(edge.dstId, (degree.get(edge.dstId) || 0) + 1);
    });
    const focusId = [...degree.entries()].sort(
      (left, right) => right[1] - left[1],
    )[0]?.[0];
    const candidateNodes = graph.nodes.filter((node) => {
      if (node.nodeId === focusId) return true;
      if (node.nodeType === "supplier") return visibility.suppliers;
      return visibility.customers;
    });
    const candidateNodeIds = new Set(candidateNodes.map((node) => node.nodeId));
    const edges = graph.edges.filter((edge) => {
      if (
        !candidateNodeIds.has(edge.srcId) ||
        !candidateNodeIds.has(edge.dstId)
      )
        return false;
      if (edge.edgeType === "SUPPLIED_BY") return visibility.supplierEdges;
      if (edge.edgeType === "CUSTOMER_OF") return visibility.customerEdges;
      return true;
    });
    const connectedNodeIds = new Set<string>(focusId ? [focusId] : []);
    edges.forEach((edge) => {
      connectedNodeIds.add(edge.srcId);
      connectedNodeIds.add(edge.dstId);
    });
    const nodes = candidateNodes.filter((node) =>
      connectedNodeIds.has(node.nodeId),
    );
    return { visibleGraph: { ...graph, nodes, edges }, focusId };
  }, [graph, visibility]);

  useEffect(() => {
    if (!containerRef.current) return;
    let disposed = false;
    let instance: G6GraphInstance | undefined;
    void import("@antv/g6").then(({ Graph }) => {
      if (disposed || !containerRef.current) return;
      const data = adaptGraph(visibleGraph, focusId);
      const shouldRestoreViewport =
        renderedDataKeyRef.current === graphDataKey && viewportStateRef.current;
      const rendered = new Graph({
        container: containerRef.current,
        autoFit: "view",
        data,
        layout: {
          type: "dagre",
          rankdir: "LR",
          nodesep: 54,
          ranksep: 150,
          controlPoints: true,
        },
        behaviors: ["drag-canvas", "zoom-canvas", "drag-element"],
        plugins: [{ type: "minimap", size: [160, 100] }],
      }) as G6GraphInstance;
      rendered.on("node:click", (event) => {
        const graphEvent = event as unknown as GraphElementEvent & {
          detail?: number;
          nativeEvent?: { detail?: number };
        };
        if ((graphEvent.detail ?? graphEvent.nativeEvent?.detail ?? 1) > 1)
          return;
        if (clickTimerRef.current) clearTimeout(clickTimerRef.current);
        const nodeId = String(graphEvent.target.id);
        clickTimerRef.current = setTimeout(() => {
          onNode(nodeId);
          clickTimerRef.current = null;
        }, NODE_CLICK_CONFIRM_DELAY_MS);
      });
      const handleNodeDoubleClick = (event: unknown) => {
        const graphEvent = event as GraphElementEvent;
        graphEvent.preventDefault?.();
        graphEvent.stopPropagation?.();
        if (clickTimerRef.current) {
          clearTimeout(clickTimerRef.current);
          clickTimerRef.current = null;
        }
        onNodeDoubleClick(String(graphEvent.target.id));
      };
      rendered.on("node:dblclick", handleNodeDoubleClick);
      rendered.on("node:doubleclick", handleNodeDoubleClick);
      rendered.on("edge:click", (event) =>
        onEdge(
          String((event as unknown as { target: { id: string } }).target.id),
        ),
      );
      rendered.on("node:contextmenu", (event) => {
        const graphEvent = event as unknown as {
          target: { id: string };
          clientX?: number;
          clientY?: number;
          client?: { x: number; y: number };
          nativeEvent?: { clientX?: number; clientY?: number };
          preventDefault?: () => void;
        };
        graphEvent.preventDefault?.();
        const bounds = containerRef.current?.getBoundingClientRect();
        const clientX =
          graphEvent.clientX ??
          graphEvent.client?.x ??
          graphEvent.nativeEvent?.clientX ??
          bounds?.left ??
          0;
        const clientY =
          graphEvent.clientY ??
          graphEvent.client?.y ??
          graphEvent.nativeEvent?.clientY ??
          bounds?.top ??
          0;
        const rawX = clientX - (bounds?.left ?? 0) + 10;
        const rawY = clientY - (bounds?.top ?? 0) + 10;
        const x = Math.max(8, Math.min(rawX, (bounds?.width ?? 170) - 152));
        const y = Math.max(8, Math.min(rawY, (bounds?.height ?? 100) - 90));
        setContextMenu({
          nodeId: String(graphEvent.target.id),
          x,
          y,
        });
      });
      rendered.on("canvas:click", () => setContextMenu(null));
      void rendered.render().then(async () => {
        if (disposed) return;
        if (shouldRestoreViewport && viewportStateRef.current) {
          await rendered.translateTo(viewportStateRef.current.position, false);
          await rendered.zoomTo(viewportStateRef.current.zoom, false);
          await rendered.draw();
        }
        renderedDataKeyRef.current = graphDataKey;
      });
      instance = rendered;
    });
    return () => {
      disposed = true;
      if (clickTimerRef.current) {
        clearTimeout(clickTimerRef.current);
        clickTimerRef.current = null;
      }
      if (instance) {
        const [x = 0, y = 0] = instance.getPosition();
        viewportStateRef.current = {
          position: [x, y],
          zoom: instance.getZoom(),
        };
      }
      instance?.destroy();
    };
  }, [focusId, graphDataKey, visibleGraph, onEdge, onNode, onNodeDoubleClick]);

  const expand = (direction: Direction) => {
    if (!contextMenu) return;
    onExpand(contextMenu.nodeId, direction);
    setContextMenu(null);
  };

  const toggleLegend = (key: LegendKey) => {
    setVisibility((current) => ({ ...current, [key]: !current[key] }));
    setContextMenu(null);
  };

  return (
    <div className="relative" onContextMenu={(event) => event.preventDefault()}>
      <div
        ref={containerRef}
        className="h-[640px] w-full rounded-2xl bg-[#edf3ff] shadow-inner ring-1 ring-blue-100"
      />
      <div className="absolute bottom-4 left-4 z-20 flex max-w-[calc(100%-2rem)] flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white/95 px-3 py-2 text-xs shadow-md backdrop-blur-sm">
        <span className="font-medium text-slate-400">图例:</span>
        {LEGEND_ITEMS.map((item) => {
          const visible = visibility[item.key];
          return (
            <button
              key={item.key}
              type="button"
              aria-pressed={visible}
              title={`点击${visible ? "隐藏" : "显示"}${item.label}`}
              onClick={() => toggleLegend(item.key)}
              className={`flex cursor-pointer items-center gap-1.5 rounded px-1 py-0.5 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                visible
                  ? "text-slate-500 hover:bg-slate-50"
                  : "text-slate-300 line-through hover:bg-slate-50"
              }`}
            >
              {item.kind === "node" ? (
                <span
                  className="h-3 w-3 rounded-full border-2 bg-white"
                  style={{
                    borderColor: item.color,
                    opacity: visible ? 1 : 0.35,
                  }}
                />
              ) : (
                <span
                  className="relative h-2 w-5"
                  style={{ opacity: visible ? 1 : 0.35 }}
                >
                  <span
                    className="absolute left-0 top-1/2 h-0.5 w-full -translate-y-1/2 rounded-full"
                    style={{ backgroundColor: item.color }}
                  />
                  <span
                    className="absolute right-0 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rotate-45 border-r-2 border-t-2"
                    style={{ borderColor: item.color }}
                  />
                </span>
              )}
              <span>{item.label}</span>
              <span aria-hidden="true">{visible ? "✓" : "×"}</span>
            </button>
          );
        })}
      </div>
      {contextMenu && (
        <div
          className="absolute z-30 w-36 overflow-hidden rounded border border-slate-100 bg-white py-1 text-xs text-slate-700 shadow-lg"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            onClick={() => expand("upstream")}
            className="block w-full cursor-pointer px-4 py-2.5 text-left leading-4 transition-colors hover:bg-slate-50 focus-visible:bg-blue-50 focus-visible:outline-none"
          >
            查询供应链
          </button>
          <button
            onClick={() => expand("downstream")}
            className="block w-full cursor-pointer px-4 py-2.5 text-left leading-4 transition-colors hover:bg-slate-50 focus-visible:bg-blue-50 focus-visible:outline-none"
          >
            查询大客户
          </button>
        </div>
      )}
    </div>
  );
}
