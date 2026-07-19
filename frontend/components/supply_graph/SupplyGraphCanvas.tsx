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
  zoomTo: (
    zoom: number,
    animation?: boolean,
    origin?: [number, number],
  ) => Promise<void>;
  resize: () => void;
  fitView: (options?: unknown, animation?: unknown) => Promise<void>;
  getClientByCanvas: (point: [number, number]) => { x: number; y: number } | number[];
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
const GRAPH_VIEW_OCCUPANCY = 0.5;

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
  // 节点越多，列间距（ranksep）拉大以清晰区分「供应商列 | 焦点 | 客户列」，
  // 同列节点间距（nodesep）略收紧以容纳更多节点；rankdir LR 保证供应关系在左、客户关系在右。
  const dense = nodeCount > 16;
  return {
    type: "dagre",
    rankdir: "LR",
    nodesep: dense ? 30 : 50,
    ranksep: dense ? 200 : 160,
    controlPoints: true,
  };
};

const scaleGraphToTargetOccupancy = async (
  instance: G6GraphInstance,
  container: HTMLElement,
) => {
  await instance.zoomTo(
    instance.getZoom() * GRAPH_VIEW_OCCUPANCY,
    false,
    [container.clientWidth / 2, container.clientHeight / 2],
  );
};

export default function SupplyGraphCanvas({
  graph,
  onNode,
  onEdge,
  onExpand,
  onNodeDoubleClick,
  expandingIds = [],
}: {
  graph: SupplyGraph;
  onNode: (id: string) => void;
  onEdge: (id: string) => void;
  onExpand: (id: string, direction: Direction) => void;
  onNodeDoubleClick: (id: string) => void;
  expandingIds?: string[];
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [spinnerPositions, setSpinnerPositions] = useState<Record<string, { x: number; y: number }>>({});
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
    // 节点角色开关（焦点/未知恒显示）
    const roleOn = (id: string) => {
      const role = roles.get(id);
      if (role === "focus" || role === undefined) return true;
      if (role === "supplier") return legend.suppliers;
      if (role === "customer") return legend.customers;
      return true;
    };
    // 边是否可见：类型开关 + 两端角色开关
    const edgeVisible = (edge: (typeof current.edges)[number]) => {
      const typeOn =
        resolveEdgeRole(edge, roles, focus) === "supply"
          ? legend.supplierEdges
          : legend.customerEdges;
      return typeOn && roleOn(edge.srcId) && roleOn(edge.dstId);
    };
    // 统计每个节点是否还有可见边，用于隐藏因关闭某类关系而产生的孤立点
    const hasVisibleEdge = new Set<string>();
    for (const edge of current.edges) {
      if (edgeVisible(edge)) {
        hasVisibleEdge.add(edge.srcId);
        hasVisibleEdge.add(edge.dstId);
      }
    }
    const nodeVisible = (id: string) => {
      if (!roleOn(id)) return false;
      if (roles.get(id) === "focus") return true; // 焦点始终显示
      return hasVisibleEdge.has(id); // 没有可见边的非焦点节点隐藏，避免孤立点
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
      try {
        instance.setElementVisibility(
          edge.edgeId,
          edgeVisible(edge) ? "visible" : "hidden",
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
      // 若有已渲染节点不在新数据中（图谱发生收缩），走全量重建。
      const incomingNodeIds = new Set(graph.nodes.map((node) => node.nodeId));
      const shrank = [...renderedNodesRef.current].some(
        (id) => !incomingNodeIds.has(id),
      );

      if (instance && !focusChanged && !layoutChanged && !shrank) {
        // 数据增长（展开某节点上下游）：**只增量添加新点边**，把新节点摆到它所连接的
        // 已有节点旁边（供应商放左、客户放右），不重跑布局、不移动已有节点、不 refit，
        // 避免整张图重排、放大或视角跳动。
        const data = adaptGraph(graph, focusId);
        const newNodes = data.nodes.filter(
          (node) => !renderedNodesRef.current.has(node.id),
        );
        const newEdges = data.edges.filter(
          (edge) => !renderedEdgesRef.current.has(edge.id),
        );
        if (!newNodes.length && !newEdges.length) return;

        const NEW_DX = 220;
        const NEW_GAP = 92;
        const byAnchor = new Map<
          string,
          { node: (typeof newNodes)[number]; role: "supply" | "customer" }[]
        >();
        for (const node of newNodes) {
          const edge = newEdges.find(
            (e) => e.source === node.id || e.target === node.id,
          );
          if (!edge) continue;
          const nodeIsSource = edge.source === node.id;
          const anchorId = nodeIsSource ? edge.target : edge.source;
          if (!renderedNodesRef.current.has(anchorId)) continue; // 锚点须为已有节点
          const role: "supply" | "customer" = nodeIsSource ? "supply" : "customer";
          const list = byAnchor.get(anchorId) ?? [];
          list.push({ node, role });
          byAnchor.set(anchorId, list);
        }
        for (const [anchorId, list] of byAnchor) {
          let ax = 0;
          let ay = 0;
          try {
            const pos = instance.getElementPosition(anchorId);
            ax = pos[0] ?? 0;
            ay = pos[1] ?? 0;
          } catch {
            continue;
          }
          const dir = list[0].role === "supply" ? -1 : 1;
          const total = list.length;
          list.forEach(({ node }, index) => {
            node.style = {
              ...node.style,
              x: ax + dir * NEW_DX,
              y: ay + (index - (total - 1) / 2) * NEW_GAP,
            };
          });
        }

        try {
          if (newNodes.length) instance.addNodeData(newNodes);
          if (newEdges.length) instance.addEdgeData(newEdges);
        } catch {
          /* 忽略：实例可能正在重建 */
        }
        void instance.draw().then(() => {
          if (disposed) return;
          renderedNodesRef.current = new Set(
            graph.nodes.map((node) => node.nodeId),
          );
          renderedEdgesRef.current = new Set(
            graph.edges.map((edge) => edge.edgeId),
          );
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
        plugins: [{
          type: "minimap",
          key: "minimap",
          size: [160, 100],
          position: "right-bottom",
          containerStyle: {
            left: "auto",
            top: "auto",
            right: "16px",
            bottom: "16px",
            borderRadius: "8px",
            overflow: "hidden",
            boxShadow: "0 4px 16px rgb(15 23 42 / 0.14)",
          },
        }],
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

      void rendered.render().then(async () => {
        if (disposed) return;
        const container = containerRef.current;
        if (!container) return;
        await scaleGraphToTargetOccupancy(rendered, container);
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

  // 容器尺寸变化（含进入/退出全屏、窗口缩放）时，同步画布尺寸并按目标占比居中，
  // 避免图谱固定在原尺寸的一角，同时防止重新铺满整个画布。
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
          void instance.fitView().then(() =>
            scaleGraphToTargetOccupancy(instance, container),
          );
          const minimap = container.querySelector<HTMLElement>(".g6-minimap");
          if (minimap) {
            Object.assign(minimap.style, {
              left: "auto",
              top: "auto",
              right: "16px",
              bottom: "16px",
            });
          }
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

  // 多节点并行扩展时，在每个节点上叠加独立旋转环，并跟随平移/缩放定位。
  useEffect(() => {
    if (!expandingIds.length) return;
    let raf = 0;
    const track = () => {
      const instance = instanceRef.current;
      const container = containerRef.current;
      if (instance && container) {
        const rect = container.getBoundingClientRect();
        const next: Record<string, { x: number; y: number }> = {};
        for (const id of expandingIds) {
          try {
            const [nx, ny] = instance.getElementPosition(id);
            const client = instance.getClientByCanvas([nx ?? 0, ny ?? 0]);
            const cx = Array.isArray(client) ? (client[0] ?? 0) : client.x;
            const cy = Array.isArray(client) ? (client[1] ?? 0) : client.y;
            next[id] = { x: cx - rect.left, y: cy - rect.top };
          } catch {
            /* 节点可能尚未渲染 */
          }
        }
        setSpinnerPositions(next);
      }
      raf = requestAnimationFrame(track);
    };
    raf = requestAnimationFrame(track);
    return () => {
      cancelAnimationFrame(raf);
      setSpinnerPositions({});
    };
  }, [expandingIds]);

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
      {/* 扩展中：在每个节点上叠加旋转环，不遮挡画布、不阻断交互 */}
      {Object.entries(spinnerPositions).map(([id, position]) => (
        <span
          key={id}
          className="pointer-events-none absolute z-30 h-16 w-16 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-blue-500/70 border-t-transparent animate-spin motion-reduce:animate-none"
          style={{ left: position.x, top: position.y }}
          aria-label="正在扩展该节点关系"
        />
      ))}
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
