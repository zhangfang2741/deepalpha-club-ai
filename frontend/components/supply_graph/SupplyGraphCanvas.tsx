"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { SupplyGraph } from "@/lib/api/supplyGraph";
import {
  adaptGraph,
  computeNodeRoles,
  resolveEdgeRole,
  type G6Node,
} from "./SupplyGraphAdapter";

type Direction = "upstream" | "downstream" | "both";
type LayoutType = "hierarchy" | "force" | "grid";
type ContextMenu = { nodeId: string; x: number; y: number } | null;
type LegendKey = "suppliers" | "customers" | "supplierEdges" | "customerEdges";
type LegendVisibility = Record<LegendKey, boolean>;
type G6GraphInstance = {
  destroy: () => void;
  draw: () => Promise<void>;
  render: () => Promise<void>;
  on: (event: string, handler: (event: unknown) => void) => void;
  setData: (data: ReturnType<typeof adaptGraph>) => void;
  addNodeData: (nodes: G6Node[]) => void;
  addEdgeData: (edges: ReturnType<typeof adaptGraph>["edges"]) => void;
  getElementPosition: (id: string) => number[];
  setElementVisibility: (id: string, visibility: "visible" | "hidden") => void;
  getPosition: () => number[];
  getZoom: () => number;
  translateTo: (position: [number, number], animation?: boolean) => Promise<void>;
  zoomTo: (zoom: number, animation?: boolean) => Promise<void>;
  resize: () => void;
  fitView: (options?: unknown, animation?: unknown) => Promise<void>;
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

const LAYOUT_OPTIONS: { value: LayoutType; label: string }[] = [
  { value: "hierarchy", label: "层次布局" },
  { value: "force", label: "力导向布局" },
  { value: "grid", label: "网格布局" },
];

const graphLayout = (layout: LayoutType, nodeCount: number) => {
  if (layout === "force") {
    return {
      type: "d3-force",
      link: { distance: 180, strength: 0.7 },
      manyBody: { strength: -650 },
      collide: { radius: 72, strength: 0.9 },
    };
  }
  if (layout === "grid") {
    return {
      type: "grid",
      cols: Math.max(1, Math.ceil(Math.sqrt(nodeCount))),
      nodeSize: 130,
      preventOverlap: true,
    };
  }
  return {
    type: "dagre",
    rankdir: "LR",
    nodesep: 54,
    ranksep: 150,
    controlPoints: true,
  };
};

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
  const currentLayoutRef = useRef<LayoutType>("hierarchy");
  const renderedNodesRef = useRef<Set<string>>(new Set());
  const renderedEdgesRef = useRef<Set<string>>(new Set());
  const clickTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastTapRef = useRef<{ id: string; time: number } | null>(null);
  const graphRef = useRef<SupplyGraph>(graph);
  const focusRef = useRef<string | undefined>(undefined);
  const visibilityRef = useRef<LegendVisibility>(INITIAL_VISIBILITY);
  const [contextMenu, setContextMenu] = useState<ContextMenu>(null);
  const [layout, setLayout] = useState<LayoutType>("hierarchy");
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

  // 按「相对焦点角色」判断显隐，与节点/边着色保持一致（隐藏只改可见性，不重排）。
  const applyVisibility = (instance: G6GraphInstance) => {
    const current = graphRef.current;
    const focus = focusRef.current;
    const roles = computeNodeRoles(current, focus);
    const legend = visibilityRef.current;
    const nodeVisible = (id: string) => {
      const role = roles.get(id);
      if (role === "focus" || role === undefined) return true;
      if (role === "supplier") return legend.suppliers;
      if (role === "customer") return legend.customers;
      return true; // unknown 始终显示
    };
    for (const node of current.nodes) {
      try {
        instance.setElementVisibility(
          node.nodeId,
          nodeVisible(node.nodeId) ? "visible" : "hidden",
        );
      } catch {
        /* 元素可能尚未渲染，忽略 */
      }
    }
    for (const edge of current.edges) {
      const typeVisible =
        resolveEdgeRole(edge, roles, focus) === "supply"
          ? legend.supplierEdges
          : legend.customerEdges;
      const visible =
        typeVisible && nodeVisible(edge.srcId) && nodeVisible(edge.dstId);
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

  useEffect(() => {
    if (!containerRef.current) return;
    let disposed = false;
    void import("@antv/g6").then(({ Graph }) => {
      if (disposed || !containerRef.current) return;
      const instance = instanceRef.current;
      const focusChanged = currentFocusRef.current !== focusId;
      const layoutChanged = currentLayoutRef.current !== layout;
      // 若有已渲染节点不在新数据中（如「返回核心关系」收缩），走全量重建。
      const incomingNodeIds = new Set(graph.nodes.map((node) => node.nodeId));
      const shrank = [...renderedNodesRef.current].some(
        (id) => !incomingNodeIds.has(id),
      );

      if (instance && !focusChanged && !layoutChanged && !shrank) {
        // 数据增长（展开）：重跑 dagre 布局以可靠地摆放新节点，但保留当前视口（缩放/平移），
        // 避免视图跳回原点。这样新点边一定会出现，同时不会突兀地重置视角。
        const data = adaptGraph(graph, focusId);
        const hasNew =
          data.nodes.some((node) => !renderedNodesRef.current.has(node.id)) ||
          data.edges.some((edge) => !renderedEdgesRef.current.has(edge.id));
        if (!hasNew) return;
        const [vx = 0, vy = 0] = instance.getPosition();
        const zoom = instance.getZoom();
        instance.setData(data);
        void instance.render().then(async () => {
          if (disposed) return;
          await instance.translateTo([vx, vy], false);
          await instance.zoomTo(zoom, false);
          renderedNodesRef.current = new Set(graph.nodes.map((node) => node.nodeId));
          renderedEdgesRef.current = new Set(graph.edges.map((edge) => edge.edgeId));
          applyVisibility(instance);
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
        layout: graphLayout(layout, graph.nodes.length),
        behaviors: ["drag-canvas", "zoom-canvas", "drag-element"],
        plugins: [{ type: "minimap", key: "minimap", size: [160, 100], position: "right-bottom" }],
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
      currentLayoutRef.current = layout;
      renderedNodesRef.current = new Set(
        graph.nodes.map((node) => node.nodeId),
      );
      renderedEdgesRef.current = new Set(
        graph.edges.map((edge) => edge.edgeId),
      );
    });
    return () => {
      disposed = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphDataKey, focusId, layout, onEdge, onNode, onNodeDoubleClick]);

  // 图例显隐：仅切换元素可见性，不改变布局与视口。
  useEffect(() => {
    visibilityRef.current = visibility;
    const instance = instanceRef.current;
    if (instance) applyVisibility(instance);
  }, [visibility]);

  // 容器尺寸变化（含进入/退出全屏、窗口缩放）时，同步画布尺寸并重新 fitView，
  // 避免图谱固定在原尺寸的一角、右侧留大片空白。
  useEffect(() => {
    const container = containerRef.current;
    if (!container || typeof ResizeObserver === "undefined") return;
    let frame = 0;
    let lastW = container.clientWidth;
    let lastH = container.clientHeight;
    const observer = new ResizeObserver(() => {
      const w = container.clientWidth;
      const h = container.clientHeight;
      if (w === 0 || h === 0 || (w === lastW && h === lastH)) return;
      lastW = w;
      lastH = h;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const instance = instanceRef.current;
        if (!instance) return;
        try {
          instance.resize();
          void instance.fitView();
        } catch {
          /* 实例可能正在重建，忽略本次 */
        }
      });
    });
    observer.observe(container);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, []);

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
    <div className="relative h-full" onContextMenu={(event) => event.preventDefault()}>
      <div
        ref={containerRef}
        className="h-full min-h-[560px] w-full touch-manipulation rounded-2xl bg-[#edf3ff] shadow-inner ring-1 ring-blue-100"
      />
      <label className="absolute right-4 top-4 z-20 flex items-center gap-2 rounded-lg border border-slate-200 bg-white/95 px-3 py-2 text-xs font-medium text-slate-500 shadow-md backdrop-blur-sm">
        <span>布局</span>
        <select
          aria-label="选择图谱布局"
          value={layout}
          onChange={(event) => {
            setContextMenu(null);
            setLayout(event.target.value as LayoutType);
          }}
          className="cursor-pointer rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
        >
          {LAYOUT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
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
