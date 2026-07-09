"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import DashboardShell from "@/components/layout/DashboardShell";
import CompanyResearchDrawer from "@/components/supply_graph/CompanyResearchDrawer";
import EdgeClueDrawer from "@/components/supply_graph/EdgeClueDrawer";
import SupplyGraphCanvas from "@/components/supply_graph/SupplyGraphCanvas";
import { mergeGraphs } from "@/components/supply_graph/SupplyGraphAdapter";
import {
  supplyGraphApi,
  type SupplyEdge,
  type SupplyGraph,
  type SupplyNode,
} from "@/lib/api/supplyGraph";
import { Loader2, RefreshCw } from "lucide-react";

const EMPTY: SupplyGraph = { nodes: [], edges: [] };
type SupplyRunTask = {
  stage?: string;
  status?: string;
  error?: string | null;
};
type SupplyRunDetail = {
  tasks?: SupplyRunTask[];
};

const sleep = (ms: number) =>
  new Promise((resolve) => window.setTimeout(resolve, ms));

const waitForSupplyRun = async (
  runId: string,
  onStage: (stage: string) => void,
) => {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    await sleep(2000);
    const detail = (await supplyGraphApi.run(runId)) as SupplyRunDetail;
    const task = detail.tasks?.[0];
    if (task?.stage) onStage(task.stage);
    if (task?.status === "success") return;
    if (task?.status === "failed")
      throw new Error(task.error || "任务执行失败");
  }
  throw new Error("生成时间较长，请稍后重新加载查看结果");
};

const DEMO: SupplyGraph = {
  nodes: [
    {
      nodeId: "NVDA",
      nodeType: "company",
      properties: [
        { name: "name", value: "NVIDIA" },
        { name: "ticker", value: "NVDA" },
        { name: "expandable", value: true },
      ],
    },
    {
      nodeId: "TSM",
      nodeType: "supplier",
      properties: [
        { name: "name", value: "Taiwan Semiconductor" },
        { name: "ticker", value: "TSM" },
        { name: "expandable", value: true },
      ],
    },
    {
      nodeId: "ASML",
      nodeType: "supplier",
      properties: [
        { name: "name", value: "ASML Holding" },
        { name: "ticker", value: "ASML" },
        { name: "expandable", value: true },
      ],
    },
    {
      nodeId: "SK_HYNIX",
      nodeType: "supplier",
      properties: [
        { name: "name", value: "SK hynix" },
        { name: "expandable", value: false },
      ],
    },
    {
      nodeId: "HON_HAI",
      nodeType: "supplier",
      properties: [
        { name: "name", value: "Hon Hai Precision" },
        { name: "expandable", value: false },
      ],
    },
    {
      nodeId: "SUMCO",
      nodeType: "supplier",
      properties: [
        { name: "name", value: "SUMCO Corporation" },
        { name: "ticker", value: "SUMCF" },
        { name: "expandable", value: true },
      ],
    },
    {
      nodeId: "MSFT",
      nodeType: "company",
      properties: [
        { name: "name", value: "Microsoft" },
        { name: "ticker", value: "MSFT" },
        { name: "expandable", value: true },
      ],
    },
    {
      nodeId: "OPENAI",
      nodeType: "company",
      properties: [
        { name: "name", value: "OpenAI" },
        { name: "expandable", value: false },
      ],
    },
    {
      nodeId: "AZURE_CLIENTS",
      nodeType: "company",
      properties: [
        { name: "name", value: "Azure Enterprise Clients" },
        { name: "expandable", value: false },
      ],
    },
  ],
  edges: [
    {
      edgeId: "demo-tsm",
      srcId: "TSM",
      dstId: "NVDA",
      edgeType: "SUPPLIED_BY",
      properties: [
        { name: "product", value: "先进制程晶圆代工" },
        { name: "confidence", value: 94 },
        { name: "confidence_source", value: "MULTI_SOURCE_VERIFIED" },
      ],
    },
    {
      edgeId: "demo-asml",
      srcId: "ASML",
      dstId: "TSM",
      edgeType: "SUPPLIED_BY",
      properties: [
        { name: "product", value: "EUV 光刻设备" },
        { name: "confidence", value: 91 },
        { name: "confidence_source", value: "SEC_VERIFIED" },
      ],
    },
    {
      edgeId: "demo-hbm",
      srcId: "SK_HYNIX",
      dstId: "NVDA",
      edgeType: "SUPPLIED_BY",
      properties: [
        { name: "product", value: "HBM 高带宽内存" },
        { name: "confidence", value: 82 },
        { name: "confidence_source", value: "SEC_VERIFIED" },
      ],
    },
    {
      edgeId: "demo-honhai",
      srcId: "HON_HAI",
      dstId: "NVDA",
      edgeType: "SUPPLIED_BY",
      properties: [
        { name: "product", value: "AI 服务器组装" },
        { name: "confidence", value: 55 },
        { name: "confidence_source", value: "UNVERIFIED" },
      ],
    },
    {
      edgeId: "demo-sumco",
      srcId: "SUMCO",
      dstId: "TSM",
      edgeType: "SUPPLIED_BY",
      properties: [
        { name: "product", value: "半导体硅晶圆" },
        { name: "confidence", value: 76 },
        { name: "confidence_source", value: "LLM" },
      ],
    },
    {
      edgeId: "demo-msft",
      srcId: "NVDA",
      dstId: "MSFT",
      edgeType: "CUSTOMER_OF",
      properties: [
        { name: "product", value: "AI 加速器与 GPU" },
        { name: "confidence", value: 92 },
        { name: "confidence_source", value: "MULTI_SOURCE_VERIFIED" },
      ],
    },
    {
      edgeId: "demo-openai",
      srcId: "MSFT",
      dstId: "OPENAI",
      edgeType: "CUSTOMER_OF",
      properties: [
        { name: "product", value: "Azure AI 算力服务" },
        { name: "confidence", value: 88 },
        { name: "confidence_source", value: "SEC_VERIFIED" },
      ],
    },
    {
      edgeId: "demo-azure",
      srcId: "OPENAI",
      dstId: "AZURE_CLIENTS",
      edgeType: "CUSTOMER_OF",
      properties: [
        { name: "product", value: "企业级 AI 模型服务" },
        { name: "confidence", value: 68 },
        { name: "confidence_source", value: "LLM" },
      ],
    },
  ],
};

const TSLA_DEMO: SupplyGraph = {
  nodes: [
    {
      nodeId: "TSLA",
      nodeType: "company",
      properties: [
        { name: "name", value: "Tesla" },
        { name: "ticker", value: "TSLA" },
        { name: "expandable", value: true },
      ],
    },
    {
      nodeId: "PCRFY",
      nodeType: "supplier",
      properties: [
        { name: "name", value: "Panasonic Holdings" },
        { name: "ticker", value: "PCRFY" },
        { name: "expandable", value: true },
      ],
    },
    {
      nodeId: "CATL",
      nodeType: "supplier",
      properties: [
        { name: "name", value: "CATL" },
        { name: "ticker", value: "300750.SZ" },
        { name: "expandable", value: true },
      ],
    },
    {
      nodeId: "LGES",
      nodeType: "supplier",
      properties: [
        { name: "name", value: "LG Energy Solution" },
        { name: "ticker", value: "373220.KS" },
        { name: "expandable", value: true },
      ],
    },
    {
      nodeId: "ALB",
      nodeType: "supplier",
      properties: [
        { name: "name", value: "Albemarle" },
        { name: "ticker", value: "ALB" },
        { name: "expandable", value: true },
      ],
    },
    {
      nodeId: "LTHM",
      nodeType: "supplier",
      properties: [
        { name: "name", value: "Arcadium Lithium" },
        { name: "ticker", value: "LTHM" },
        { name: "expandable", value: true },
      ],
    },
    {
      nodeId: "HTZ",
      nodeType: "company",
      properties: [
        { name: "name", value: "Hertz Global" },
        { name: "ticker", value: "HTZ" },
        { name: "expandable", value: true },
      ],
    },
    {
      nodeId: "FLEET_CUSTOMERS",
      nodeType: "company",
      properties: [
        { name: "name", value: "Commercial Fleet Customers" },
        { name: "expandable", value: false },
      ],
    },
  ],
  edges: [
    {
      edgeId: "tesla-panasonic",
      srcId: "PCRFY",
      dstId: "TSLA",
      edgeType: "SUPPLIED_BY",
      properties: [
        { name: "product", value: "圆柱形动力电池" },
        { name: "confidence", value: 94 },
        { name: "confidence_source", value: "MULTI_SOURCE_VERIFIED" },
      ],
    },
    {
      edgeId: "tesla-catl",
      srcId: "CATL",
      dstId: "TSLA",
      edgeType: "SUPPLIED_BY",
      properties: [
        { name: "product", value: "磷酸铁锂动力电池" },
        { name: "confidence", value: 92 },
        { name: "confidence_source", value: "MULTI_SOURCE_VERIFIED" },
      ],
    },
    {
      edgeId: "tesla-lg",
      srcId: "LGES",
      dstId: "TSLA",
      edgeType: "SUPPLIED_BY",
      properties: [
        { name: "product", value: "2170 锂离子电池" },
        { name: "confidence", value: 86 },
        { name: "confidence_source", value: "SEC_VERIFIED" },
      ],
    },
    {
      edgeId: "catl-alb",
      srcId: "ALB",
      dstId: "CATL",
      edgeType: "SUPPLIED_BY",
      properties: [
        { name: "product", value: "电池级锂材料" },
        { name: "confidence", value: 73 },
        { name: "confidence_source", value: "LLM" },
      ],
    },
    {
      edgeId: "panasonic-lithium",
      srcId: "LTHM",
      dstId: "PCRFY",
      edgeType: "SUPPLIED_BY",
      properties: [
        { name: "product", value: "氢氧化锂" },
        { name: "confidence", value: 64 },
        { name: "confidence_source", value: "UNVERIFIED" },
      ],
    },
    {
      edgeId: "tesla-hertz",
      srcId: "TSLA",
      dstId: "HTZ",
      edgeType: "CUSTOMER_OF",
      properties: [
        { name: "product", value: "Model 3 / Model Y 车队" },
        { name: "confidence", value: 89 },
        { name: "confidence_source", value: "MULTI_SOURCE_VERIFIED" },
      ],
    },
    {
      edgeId: "hertz-fleet",
      srcId: "HTZ",
      dstId: "FLEET_CUSTOMERS",
      edgeType: "CUSTOMER_OF",
      properties: [
        { name: "product", value: "电动车租赁服务" },
        { name: "confidence", value: 74 },
        { name: "confidence_source", value: "LLM" },
      ],
    },
  ],
};

export const demoNeighborhood = (
  seed: string,
  depth: number,
  direction: string,
): SupplyGraph => {
  const source =
    seed === "TSLA" || TSLA_DEMO.nodes.some((node) => node.nodeId === seed)
      ? TSLA_DEMO
      : DEMO;
  if (!source.nodes.some((node) => node.nodeId === seed)) return EMPTY;
  const normalizedSeed = seed;
  const visited = new Set([normalizedSeed]);
  let frontier = new Set([normalizedSeed]);
  const selectedEdges = new Map<string, SupplyGraph["edges"][number]>();
  for (let hop = 0; hop < depth; hop += 1) {
    const next = new Set<string>();
    for (const edge of source.edges) {
      const upstream =
        edge.edgeType === "SUPPLIED_BY" && frontier.has(edge.dstId);
      const downstream =
        edge.edgeType === "CUSTOMER_OF" && frontier.has(edge.srcId);
      const connected = frontier.has(edge.srcId) || frontier.has(edge.dstId);
      if (
        (direction === "upstream" && upstream) ||
        (direction === "downstream" && downstream) ||
        (direction === "both" && connected)
      ) {
        selectedEdges.set(edge.edgeId, edge);
        next.add(edge.srcId);
        next.add(edge.dstId);
      }
    }
    frontier = new Set([...next].filter((id) => !visited.has(id)));
    frontier.forEach((id) => visited.add(id));
  }
  return {
    nodes: source.nodes.filter((node) => visited.has(node.nodeId)),
    edges: [...selectedEdges.values()],
  };
};

export default function SupplyGraphPage() {
  const [ticker, setTicker] = useState("NVDA");
  const [query, setQuery] = useState("NVDA");
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [graph, setGraph] = useState<SupplyGraph>(EMPTY);
  const [exploring, setExploring] = useState(false);
  const [loading, setLoading] = useState(true);
  const [expanding, setExpanding] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState("");
  const [feedback, setFeedback] = useState("正在加载核心供应链…");
  const [errorMessage, setErrorMessage] = useState("");
  const [selectedEdge, setSelectedEdge] = useState<SupplyEdge | null>(null);
  const [selectedNode, setSelectedNode] = useState<SupplyNode | null>(null);
  const [clues, setClues] = useState<Record<string, unknown>[]>([]);
  useEffect(() => {
    let cancelled = false;
    void supplyGraphApi
      .graph(ticker, 1, "both")
      .then((data) => {
        if (!cancelled) {
          setGraph(data);
          setFeedback(
            data.nodes.length ? "图谱已更新" : "暂无已生成的核心关系",
          );
          setErrorMessage("");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setGraph(EMPTY);
          setErrorMessage("图谱加载失败，请点击“重新加载”重试。");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker, refreshVersion]);
  const coreGraph = useMemo(() => {
    const confidence = (edge: SupplyGraph["edges"][number]) =>
      Number(
        edge.properties.find((property) => property.name === "confidence")
          ?.value || 0,
      );
    const suppliers = graph.edges
      .filter(
        (edge) => edge.edgeType === "SUPPLIED_BY" && edge.dstId === ticker,
      )
      .sort((left, right) => confidence(right) - confidence(left));
    const customers = graph.edges
      .filter(
        (edge) => edge.edgeType === "CUSTOMER_OF" && edge.srcId === ticker,
      )
      .sort((left, right) => confidence(right) - confidence(left));
    const edges = [...suppliers, ...customers];
    const nodeIds = new Set([
      ticker,
      ...edges.flatMap((edge) => [edge.srcId, edge.dstId]),
    ]);
    return {
      nodes: graph.nodes.filter((node) => nodeIds.has(node.nodeId)),
      edges,
      truncated: graph.truncated,
    };
  }, [graph, ticker]);
  const supplierCount = coreGraph.edges.filter(
    (edge) => edge.edgeType === "SUPPLIED_BY",
  ).length;
  const customerCount = coreGraph.edges.filter(
    (edge) => edge.edgeType === "CUSTOMER_OF",
  ).length;
  const visibleGraph = exploring ? graph : coreGraph;
  const nodeDisplayName = useCallback(
    (id: string) => {
      const node = graph.nodes.find((item) => item.nodeId === id);
      const values = Object.fromEntries(
        (node?.properties || []).map((property) => [
          property.name,
          property.value,
        ]),
      );
      return String(values.name_zh || values.ticker || values.name || id);
    },
    [graph.nodes],
  );
  const nodeTicker = useCallback(
    (id: string) => {
      const node = graph.nodes.find((item) => item.nodeId === id);
      const values = Object.fromEntries(
        (node?.properties || []).map((property) => [
          property.name,
          property.value,
        ]),
      );
      const tickerValue = values.ticker || id;
      const tickerText = String(tickerValue || "").trim().toUpperCase();
      if (!/^[A-Z][A-Z0-9.-]{0,7}$/.test(tickerText)) return "";
      return tickerText;
    },
    [graph.nodes],
  );
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setExploring(false);
    setLoading(true);
    setFeedback(`正在查询 ${query.trim().toUpperCase()}…`);
    setErrorMessage("");
    setTicker(query.trim().toUpperCase());
    setRefreshVersion((version) => version + 1);
  };
  const handleDirectionalExpand = useCallback(
    async (id: string, expandDirection: "upstream" | "downstream" | "both") => {
      const name = nodeDisplayName(id);
      try {
        setExpanding(true);
        setFeedback(`正在扩展 ${name}…`);
        setExploring(true);
        const next = await supplyGraphApi.expand(id, 1, expandDirection);
        setGraph((current) => mergeGraphs(current, next));
        setFeedback(`已完成 ${name} 的关系扩展`);
      } catch {
        setErrorMessage(`无法扩展 ${name}，请稍后重试。`);
      } finally {
        setExpanding(false);
      }
    },
    [nodeDisplayName],
  );
  const handleBidirectionalExpand = useCallback(async (id: string) => {
    const name = nodeDisplayName(id);
    const focusTicker = nodeTicker(id);
    try {
      setSelectedNode(null);
      setSelectedEdge(null);
      setClues([]);
      setExpanding(true);
      setErrorMessage("");
      setFeedback(
        focusTicker
          ? `正在基于真实环境分析 ${name} 的供应链和大客户…`
          : `正在同时扩展 ${name} 的供应链和大客户…`,
      );
      setExploring(true);
      if (focusTicker) {
        setProgress("DISCOVER");
        const created = (await supplyGraphApi.runCompany(focusTicker)) as {
          run_id: string;
        };
        await waitForSupplyRun(created.run_id, setProgress);
      }
      setFeedback(`正在合并 ${name} 的上下游关系…`);
      const expandSeed = focusTicker || id;
      const [upstream, downstream] = await Promise.all([
        supplyGraphApi.expand(expandSeed, 1, "upstream"),
        supplyGraphApi.expand(expandSeed, 1, "downstream"),
      ]);
      const incoming = mergeGraphs(upstream, downstream);
      const currentNodeIds = new Set(graph.nodes.map((node) => node.nodeId));
      const currentEdgeIds = new Set(graph.edges.map((edge) => edge.edgeId));
      const newNodeCount = incoming.nodes.filter(
        (node) => !currentNodeIds.has(node.nodeId),
      ).length;
      const newEdgeCount = incoming.edges.filter(
        (edge) => !currentEdgeIds.has(edge.edgeId),
      ).length;
      setGraph((current) => mergeGraphs(current, incoming));
      setFeedback(
        newNodeCount || newEdgeCount
          ? `已新增 ${name} 的 ${newNodeCount} 个企业点、${newEdgeCount} 条关系`
          : `${name} 暂无新增上下游关系`,
      );
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : `无法扩展 ${name} 的上下游关系，请稍后重试。`,
      );
    } finally {
      setExpanding(false);
      setProgress("");
    }
  }, [graph.edges, graph.nodes, nodeDisplayName, nodeTicker]);
  const handleEdge = useCallback(
    async (id: string) => {
      setSelectedNode(null);
      setSelectedEdge(graph.edges.find((edge) => edge.edgeId === id) || null);
      setClues([]);
      try {
        setClues(await supplyGraphApi.clues(id));
      } catch {
        setClues([]);
      }
    },
    [graph.edges],
  );
  const handleNode = useCallback(
    (id: string) => {
      setSelectedEdge(null);
      setClues([]);
      setSelectedNode(graph.nodes.find((node) => node.nodeId === id) || null);
    },
    [graph.nodes],
  );
  const generateGraph = async () => {
    try {
      setGenerating(true);
      setErrorMessage("");
      setProgress("DISCOVER");
      setFeedback(`正在分析 ${ticker} 的核心供应商和大客户…`);
      const created = await supplyGraphApi.runCompany(ticker);
      await waitForSupplyRun(created.run_id, setProgress);
      setFeedback(`${ticker} 的核心关系已生成`);
      setRefreshVersion((version) => version + 1);
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "生成失败，请稍后重试。",
      );
    } finally {
      setGenerating(false);
      setProgress("");
    }
  };
  return (
    <DashboardShell>
      <main className="min-h-screen overflow-x-hidden bg-slate-50 p-3 sm:p-6">
        <div className="mx-auto max-w-[1500px]">
          <header className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div className="min-w-0">
              <p className="text-sm font-medium text-blue-600">
                SUPPLY INTELLIGENCE
              </p>
              <h1 className="text-wrap-balance text-3xl font-bold text-slate-900">
                美股供应链图谱
              </h1>
              <p className="mt-1 text-slate-500">
                聚焦每家公司的核心供应商与大客户。
              </p>
            </div>
            <div className="flex w-full min-w-0 flex-wrap items-center gap-2 sm:w-auto">
            <Link
              href="/supply-graph/tasks"
              className="inline-flex shrink-0 items-center gap-2 rounded-xl border bg-white px-4 py-2 text-slate-600 transition-colors hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-blue-500"
            >
              任务看板
            </Link>
            <form
              onSubmit={submit}
              className="flex w-full min-w-0 gap-2 sm:w-auto"
            >
              <label htmlFor="supply-graph-ticker" className="sr-only">
                股票代码
              </label>
              <input
                id="supply-graph-ticker"
                name="ticker"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                autoComplete="off"
                spellCheck={false}
                className="min-w-0 flex-1 rounded-xl border bg-white px-4 py-2 transition-colors focus-visible:ring-2 focus-visible:ring-blue-500 sm:w-52 sm:flex-none"
                placeholder="Ticker，例如 NVDA…"
              />
              <button
                disabled={loading}
                className="inline-flex shrink-0 cursor-pointer items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-white transition-colors hover:bg-blue-700 focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-60 sm:px-5"
              >
                {loading && (
                  <Loader2
                    aria-hidden="true"
                    className="h-4 w-4 animate-spin motion-reduce:animate-none"
                  />
                )}
                {loading ? "查询中…" : "查询公司"}
              </button>
            </form>
            </div>
          </header>
          <div
            aria-live="polite"
            className={`mb-4 flex min-h-10 flex-wrap items-center justify-between gap-2 rounded-xl border px-4 py-2 text-sm ${errorMessage ? "border-red-200 bg-red-50 text-red-700" : "border-blue-100 bg-blue-50 text-blue-700"}`}
          >
            <span>{errorMessage || feedback}</span>
            {errorMessage && (
              <button
                onClick={() => {
                  setLoading(true);
                  setRefreshVersion((version) => version + 1);
                }}
                className="inline-flex cursor-pointer items-center gap-1 rounded-lg px-2 py-1 font-medium hover:bg-red-100 focus-visible:ring-2 focus-visible:ring-red-500"
              >
                <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
                重新加载
              </button>
            )}
          </div>
          <section className="relative overflow-hidden rounded-2xl border bg-white p-4 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex flex-wrap items-center gap-2 text-sm sm:gap-3">
                <span className="rounded-full bg-emerald-50 px-3 py-1.5 font-medium text-emerald-700">
                  核心供应商 {supplierCount}
                </span>
                <span className="rounded-full bg-blue-50 px-3 py-1.5 font-medium text-blue-700">
                  大客户 {customerCount}
                </span>
                <span className="text-xs text-slate-400">
                  数量由模型按核心关系标准判断
                </span>
                {exploring && (
                  <button
                    onClick={() => setExploring(false)}
                    className="cursor-pointer rounded-lg border px-3 py-1.5 text-slate-600 transition-colors hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-blue-500"
                  >
                    返回核心关系
                  </button>
                )}
              </div>
              {graph.truncated && (
                <span className="rounded-full bg-amber-100 px-3 py-1 text-xs text-amber-800">
                  已按重要性截断
                </span>
              )}
            </div>
            {loading ? (
              <div className="flex h-[640px] items-center justify-center text-slate-500">
                正在加载图谱…
              </div>
            ) : visibleGraph.nodes.length ? (
              <div className="relative">
                <SupplyGraphCanvas
                  graph={visibleGraph}
                  onNode={handleNode}
                  onEdge={handleEdge}
                  onExpand={handleDirectionalExpand}
                  onNodeDoubleClick={handleBidirectionalExpand}
                />
                {expanding && (
                  <div
                    className="absolute inset-0 z-20 flex items-center justify-center rounded-2xl bg-slate-950/45 backdrop-blur-[1px]"
                    aria-live="polite"
                  >
                    <div className="flex items-center gap-3 rounded-xl bg-white px-5 py-3 text-sm font-medium text-slate-700 shadow-xl">
                      <Loader2
                        aria-hidden="true"
                        className="h-5 w-5 animate-spin text-blue-600 motion-reduce:animate-none"
                      />
                      正在扩展关系…
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex h-[640px] flex-col items-center justify-center gap-3 text-slate-500">
                <p>该公司暂无图谱数据</p>
                {generating && (
                  <div className="flex gap-2 text-xs" aria-live="polite">
                    {["DISCOVER", "RESOLVE", "EVIDENCE_VERIFY"].map((stage) => (
                      <span
                        key={stage}
                        className={`rounded-full px-3 py-1 ${progress === stage ? "bg-blue-100 font-semibold text-blue-700" : "bg-slate-100 text-slate-400"}`}
                      >
                        {stage}
                      </span>
                    ))}
                  </div>
                )}
                <button
                  onClick={generateGraph}
                  disabled={generating}
                  className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-white transition-colors hover:bg-slate-700 focus-visible:ring-2 focus-visible:ring-slate-500 focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-60"
                >
                  {generating && (
                    <Loader2
                      aria-hidden="true"
                      className="h-4 w-4 animate-spin motion-reduce:animate-none"
                    />
                  )}
                  {generating ? "生成中…" : `生成 ${ticker} 核心关系`}
                </button>
              </div>
            )}
            <EdgeClueDrawer
              edge={selectedEdge}
              sourceNode={
                selectedEdge
                  ? graph.nodes.find(
                      (node) => node.nodeId === selectedEdge.srcId,
                    ) || null
                  : null
              }
              targetNode={
                selectedEdge
                  ? graph.nodes.find(
                      (node) => node.nodeId === selectedEdge.dstId,
                    ) || null
                  : null
              }
              clues={clues}
              onClose={() => setSelectedEdge(null)}
            />
            <CompanyResearchDrawer
              node={selectedNode}
              onClose={() => setSelectedNode(null)}
            />
          </section>
        </div>
      </main>
    </DashboardShell>
  );
}
