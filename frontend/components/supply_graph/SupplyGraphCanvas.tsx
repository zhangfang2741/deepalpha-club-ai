"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { SupplyGraph } from "@/lib/api/supplyGraph";
import { adaptGraph, type G6Node } from "./SupplyGraphAdapter";

type Direction = "upstream" | "downstream" | "both";
type ContextMenu = { nodeId: string; x: number; y: number } | null;
type LegendKey = "suppliers" | "customers" | "supplierEdges" | "customerEdges";
type LegendVisibility = Record<LegendKey, boolean>;
type G6GraphInstance = {
  destroy: () => void;
  draw: () => Promise<void>;
  render: () => Promise<void>;
  on: (event: string, handler: (event: unknown) => void) => void;
  addNodeData: (nodes: G6Node[]) => void;
  addEdgeData: (edges: ReturnType<typeof adaptGraph>["edges"]) => void;
  getElementPosition: (id: string) => number[];
  setElementVisibility: (id: string, visibility: "visible" | "hidden") => void;
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
const EXPAND_X_STEP = 210;
const EXPAND_Y_STEP = 96;

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
  const instanceRef = useRef<G6GraphInstance | null>(null);
  const currentFocusRef = useRef<string | undefined>(undefined);
  const renderedNodesRef = useRef<Set<string>>(new Set());
  const renderedEdgesRef = useRef<Set<string>>(new Set());
  const anchorCountRef = useRef<Map<string, number>>(new Map());
  const clickTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastTapRef = useRef<{ id: string; time: number } | null>(null);
  const graphRef = useRef<SupplyGraph>(graph);
  const focusRef = useRef<string | undefined>(undefined);
  const visibilityRef = useRef<LegendVisibility>(INITIAL_VISIBILITY);
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

  // 焦点：连接度最高的节点。用作 dagre 布局的中心与初次渲染的高亮点。
  const focusId = useMemo(() => {
    const degree = new Map<string, number>();
    graph.edges.forEach((edge) => {
      degree.set(edge.srcId, (degree.get(edge.srcId) || 0) + 1);
      degree.set(edge.dstId, (degree.get(edge.dstId) || 0) + 1);
    });
    return [...degree.entries()].sort(
      (left, right) => right[1] - left[1],
    )[0]?.[0];
  }, [graph]);

  // 同步最新 graph/focus 到 ref，供各 effect（增量放置、可见性）读取最新值。
  // 声明在主 effect 之前，保证同一次提交里先更新 ref 再运行下面的 effect。
  useEffect(() => {
    graphRef.current = graph;
    focusRef.current = focusId;
  });

  // 每个节点/边在当前图例下是否应可见（隐藏只改可见性，不触发重新布局）。
  const nodeVisible = (nodeType: string | undefined, isFocus: boolean) =>
    isFocus ||
    (nodeType === "supplier"
      ? visibilityRef.current.suppliers
      : visibilityRef.current.customers);

  const applyVisibility = (instance: G6GraphInstance) => {
    const current = graphRef.current;
    const focus = focusRef.current;
    const typeById = new Map(
      current.nodes.map((node) => [node.nodeId, node.nodeType]),
    );
    for (const node of current.nodes) {
      const visible = nodeVisible(node.nodeType, node.nodeId === focus);
      try {
        instance.setElementVisibility(
          node.nodeId,
          visible ? "visible" : "hidden",
        );
      } catch {
        /* 元素可能尚未渲染，忽略 */
      }
    }
    for (const edge of current.edges) {
      const srcVisible = nodeVisible(
        typeById.get(edge.srcId),
        edge.srcId === focus,
      );
      const dstVisible = nodeVisible(
        typeById.get(edge.dstId),
        edge.dstId === focus,
      );
      const typeVisible =
        edge.edgeType === "SUPPLIED_BY"
          ? visibilityRef.current.supplierEdges
          : visibilityRef.current.customerEdges;
      const visible = typeVisible && srcVisible && dstVisible;
      try {
        instance.setElementVisibility(
          edge.edgeId,
          visible ? "visible" : "hidden",
        );
      } catch {
        /* 元素可能尚未渲染，忽略 */
      }
    }
  };

  // 为新增节点就近分配坐标（相连的已有节点旁），从而不触发全局重新布局。
  const placeNode = (instance: G6GraphInstance, node: G6Node) => {
    const current = graphRef.current;
    let anchorId: string | undefined;
    let side = 1;
    for (const edge of current.edges) {
      if (edge.srcId === node.id && renderedNodesRef.current.has(edge.dstId)) {
        anchorId = edge.dstId;
        side = edge.edgeType === "SUPPLIED_BY" ? -1 : 1;
        break;
      }
      if (edge.dstId === node.id && renderedNodesRef.current.has(edge.srcId)) {
        anchorId = edge.srcId;
        side = edge.edgeType === "SUPPLIED_BY" ? 1 : -1;
        break;
      }
    }
    let baseX = 0;
    let baseY = 0;
    if (anchorId) {
      const [ax = 0, ay = 0] = instance.getElementPosition(anchorId);
      baseX = ax;
      baseY = ay;
    }
    const count = anchorCountRef.current.get(anchorId ?? node.id) ?? 0;
    anchorCountRef.current.set(anchorId ?? node.id, count + 1);
    const offset = Math.ceil((count + 1) / 2) * EXPAND_Y_STEP;
    node.style.x = baseX + side * EXPAND_X_STEP;
    node.style.y = baseY + (count % 2 === 0 ? offset : -offset);
  };

  useEffect(() => {
    if (!containerRef.current) return;
    let disposed = false;
    void import("@antv/g6").then(({ Graph }) => {
      if (disposed || !containerRef.current) return;
      const instance = instanceRef.current;
      const focusChanged = currentFocusRef.current !== focusId;
      // 若有已渲染节点不在新数据中（如「返回核心关系」收缩），走全量重建。
      const incomingNodeIds = new Set(graph.nodes.map((node) => node.nodeId));
      const shrank = [...renderedNodesRef.current].some(
        (id) => !incomingNodeIds.has(id),
      );

      if (instance && !focusChanged && !shrank) {
        // 增量更新：只加入新点边，已有节点位置与视口保持不变。
        const data = adaptGraph(graph, focusId);
        const newNodes = data.nodes.filter(
          (node) => !renderedNodesRef.current.has(node.id),
        );
        const newEdges = data.edges.filter(
          (edge) => !renderedEdgesRef.current.has(edge.id),
        );
        if (newNodes.length === 0 && newEdges.length === 0) return;
        newNodes.forEach((node) => placeNode(instance, node));
        newNodes.forEach((node) => renderedNodesRef.current.add(node.id));
        newEdges.forEach((edge) => renderedEdgesRef.current.add(edge.id));
        if (newNodes.length) instance.addNodeData(newNodes);
        if (newEdges.length) instance.addEdgeData(newEdges);
        void instance.draw().then(() => {
          if (!disposed) applyVisibility(instance);
        });
        return;
      }

      // 首次渲染或切换焦点公司：全量创建并跑一次 dagre 布局。
      instance?.destroy();
      const data = adaptGraph(graph, focusId);
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
      }) as unknown as G6GraphInstance;

      const handleNodeDoubleClick = (nodeId: string) => {
        if (clickTimerRef.current) {
          clearTimeout(clickTimerRef.current);
          clickTimerRef.current = null;
        }
        lastTapRef.current = null;
        onNodeDoubleClick(nodeId);
      };
      // 手动检测双击：触屏不触发原生 dblclick，统一用「同节点 320ms 内两次点击」判定。
      rendered.on("node:click", (event) => {
        const graphEvent = event as unknown as GraphElementEvent;
        const nodeId = String(graphEvent.target.id);
        const now = Date.now();
        const last = lastTapRef.current;
        if (
          last &&
          last.id === nodeId &&
          now - last.time < NODE_CLICK_CONFIRM_DELAY_MS
        ) {
          handleNodeDoubleClick(nodeId);
          return;
        }
        lastTapRef.current = { id: nodeId, time: now };
        if (clickTimerRef.current) clearTimeout(clickTimerRef.current);
        clickTimerRef.current = setTimeout(() => {
          onNode(nodeId);
          clickTimerRef.current = null;
          lastTapRef.current = null;
        }, NODE_CLICK_CONFIRM_DELAY_MS);
      });
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
        setContextMenu({ nodeId: String(graphEvent.target.id), x, y });
      });
      rendered.on("canvas:click", () => setContextMenu(null));

      void rendered.render().then(() => {
        if (disposed) return;
        applyVisibility(rendered);
      });
      instanceRef.current = rendered;
      currentFocusRef.current = focusId;
      renderedNodesRef.current = new Set(
        graph.nodes.map((node) => node.nodeId),
      );
      renderedEdgesRef.current = new Set(
        graph.edges.map((edge) => edge.edgeId),
      );
      anchorCountRef.current = new Map();
    });
    return () => {
      disposed = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphDataKey, focusId, onEdge, onNode, onNodeDoubleClick]);

  // 图例显隐：仅切换元素可见性，不改变布局与视口。
  useEffect(() => {
    visibilityRef.current = visibility;
    const instance = instanceRef.current;
    if (instance) applyVisibility(instance);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibility]);

  // 组件卸载时销毁实例。
  useEffect(
    () => () => {
      if (clickTimerRef.current) clearTimeout(clickTimerRef.current);
      instanceRef.current?.destroy();
      instanceRef.current = null;
    },
    [],
  );

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
        className="h-[640px] w-full touch-manipulation rounded-2xl bg-[#edf3ff] shadow-inner ring-1 ring-blue-100"
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
