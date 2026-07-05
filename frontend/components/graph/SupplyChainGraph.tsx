'use client'

import { useCallback, useEffect, useMemo, useRef } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeTypes,
  type ReactFlowInstance,
  MarkerType,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import dagre from '@dagrejs/dagre'

import type { EntityType, GraphData, GraphEdge, GraphNode } from '@/lib/api/supply_chain'
import { ENTITY_COLORS, RELATION_COLORS, RELATION_LABELS } from './GraphLegend'

// ── 自定义节点 ──────────────────────────────────
interface EntityNodeData {
  label: string
  entity_type: EntityType
  ticker: string | null
  fact_count: number
  [key: string]: unknown
}

function EntityNode({ data, selected }: { data: EntityNodeData; selected?: boolean }) {
  const color = ENTITY_COLORS[data.entity_type]
  const size = Math.max(40, Math.min(80, 30 + data.fact_count * 4))

  return (
    <div
      className={`rounded-xl border-2 bg-white shadow-md transition-all cursor-pointer ${
        selected ? 'shadow-lg scale-105' : 'hover:shadow-md hover:scale-102'
      }`}
      style={{
        borderColor: color,
        minWidth: `${size + 40}px`,
        maxWidth: '160px',
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: color, width: 8, height: 8 }} />

      {/* 类型色标 */}
      <div className="rounded-t-lg px-2 py-1 text-white text-center" style={{ backgroundColor: color }}>
        <span className="text-[10px] font-semibold uppercase tracking-wider">{data.entity_type}</span>
      </div>

      {/* 内容 */}
      <div className="px-2 py-1.5 text-center">
        <p className="text-xs font-semibold text-gray-800 leading-tight break-words">{data.label}</p>
        {data.ticker && (
          <p className="text-[10px] text-gray-400 mt-0.5">{data.ticker}</p>
        )}
        {data.fact_count > 0 && (
          <div
            className="mt-1 text-[9px] text-white rounded-full px-1.5 inline-block"
            style={{ backgroundColor: color + 'cc' }}
          >
            {data.fact_count} 条事实
          </div>
        )}
      </div>

      <Handle type="source" position={Position.Right} style={{ background: color, width: 8, height: 8 }} />
    </div>
  )
}

const nodeTypes: NodeTypes = { entity: EntityNode as NodeTypes['entity'] }

// ── 布局算法（dagre 左右层次布局）──────────────────
// 节点尺寸估算（与 EntityNode 渲染尺寸一致，供 dagre 计算间距用）
const NODE_WIDTH = 170
const NODE_HEIGHT = 96

function layoutNodes(graphNodes: GraphNode[], graphEdges: GraphEdge[]): Node[] {
  const g = new dagre.graphlib.Graph()
  g.setGraph({
    rankdir: 'LR', // 从左到右分层
    nodesep: 36, // 同层节点间距
    ranksep: 140, // 层与层间距
    marginx: 40,
    marginy: 40,
  })
  g.setDefaultEdgeLabel(() => ({}))

  for (const n of graphNodes) {
    g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  }
  for (const e of graphEdges) {
    // 只连接存在于当前节点集合中的边，避免 dagre 报错
    if (g.hasNode(e.source) && g.hasNode(e.target)) {
      g.setEdge(e.source, e.target)
    }
  }

  dagre.layout(g)

  return graphNodes.map((n) => {
    const pos = g.node(n.id)
    return {
      id: n.id,
      type: 'entity',
      // dagre 返回节点中心坐标，React Flow 用左上角，需减去半宽高
      position: {
        x: (pos?.x ?? 0) - NODE_WIDTH / 2,
        y: (pos?.y ?? 0) - NODE_HEIGHT / 2,
      },
      data: {
        label: n.name,
        entity_type: n.entity_type,
        ticker: n.ticker,
        fact_count: n.fact_count,
      },
    }
  })
}

function buildEdges(graphEdges: GraphEdge[]): Edge[] {
  return graphEdges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: RELATION_LABELS[e.relation_type],
    style: { stroke: RELATION_COLORS[e.relation_type], strokeWidth: 1.5 },
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: RELATION_COLORS[e.relation_type],
    },
    type: 'smoothstep',
    animated: e.relation_type === 'CONSTRAINED_BY',
    data: {
      evidence_text: e.evidence_text,
      confidence: e.confidence,
      event_time: e.event_time,
      document_url: e.document_url,
      relation_type: e.relation_type,
    },
    labelStyle: {
      fontSize: 9,
      fill: RELATION_COLORS[e.relation_type],
      fontWeight: 600,
    },
    labelBgStyle: { fill: '#fff', fillOpacity: 0.85 },
    labelBgPadding: [2, 4] as [number, number],
  }))
}

// ── 主组件 ──────────────────────────────────────
interface SupplyChainGraphProps {
  graphData: GraphData
  onNodeClick?: (nodeId: string) => void
  onEdgeClick?: (edgeId: string, evidence: string, docUrl?: string | null) => void
  onIngestClick?: () => void
}

export default function SupplyChainGraph({ graphData, onNodeClick, onEdgeClick, onIngestClick }: SupplyChainGraphProps) {
  const initialNodes = useMemo(() => layoutNodes(graphData.nodes, graphData.edges), [graphData.nodes, graphData.edges])
  const initialEdges = useMemo(() => buildEdges(graphData.edges), [graphData.edges])

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  const rfRef = useRef<ReactFlowInstance | null>(null)

  // graphData 异步加载/过滤刷新后，useNodesState/useEdgesState 不会自动跟随
  // 初值变化，必须手动同步，否则画布始终停留在首次渲染时的空数据。
  useEffect(() => {
    setNodes(initialNodes)
    setEdges(initialEdges)
    // 等待新节点提交到 DOM 后再适配视图（fitView 仅在挂载时自动执行一次）。
    const id = requestAnimationFrame(() => {
      rfRef.current?.fitView({ padding: 0.15 })
    })
    return () => cancelAnimationFrame(id)
  }, [initialNodes, initialEdges, setNodes, setEdges])

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      onNodeClick?.(node.id)
    },
    [onNodeClick],
  )

  const handleEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => {
      onEdgeClick?.(
        edge.id,
        (edge.data as { evidence_text?: string })?.evidence_text ?? '',
        (edge.data as { document_url?: string })?.document_url,
      )
    },
    [onEdgeClick],
  )

  if (graphData.nodes.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-50 rounded-xl border border-dashed border-gray-300">
        <div className="text-center">
          <p className="text-gray-400 text-sm">图谱暂无数据</p>
          <p className="text-gray-300 text-xs mt-1">先在第一步导入文档，系统会自动抽取产业链事实</p>
          {onIngestClick && (
            <button
              onClick={onIngestClick}
              className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded-lg transition-colors"
            >
              前往第一步 · 摄取数据
            </button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onEdgeClick={handleEdgeClick}
        onInit={(instance) => { rfRef.current = instance }}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.2}
        maxZoom={2}
        defaultEdgeOptions={{ type: 'smoothstep' }}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#e5e7eb" gap={20} />
        <Controls showInteractive={false} />
        <MiniMap
          nodeColor={(node) => ENTITY_COLORS[(node.data as EntityNodeData).entity_type] ?? '#999'}
          nodeStrokeWidth={3}
          zoomable
          pannable
          style={{ backgroundColor: '#f9fafb', border: '1px solid #e5e7eb' }}
        />
      </ReactFlow>
    </div>
  )
}
