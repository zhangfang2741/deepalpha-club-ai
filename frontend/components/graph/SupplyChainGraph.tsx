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

import type { EntityType, GraphData, GraphEdge, GraphNode, RelationType } from '@/lib/api/supply_chain'
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
      <Handle type="target" position={Position.Top} style={{ background: color, width: 8, height: 8 }} />

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

      <Handle type="source" position={Position.Bottom} style={{ background: color, width: 8, height: 8 }} />
    </div>
  )
}

const nodeTypes: NodeTypes = { entity: EntityNode as NodeTypes['entity'] }

// ── 布局算法（简单分层）──────────────────────────
const TYPE_LAYER: Record<EntityType, number> = {
  Concept: 0,
  Company: 1,
  Product: 2,
  Technology: 3,
  Resource: 4,
}

function layoutNodes(graphNodes: GraphNode[]): Node[] {
  const byLayer: Record<number, GraphNode[]> = {}
  for (const n of graphNodes) {
    const layer = TYPE_LAYER[n.entity_type] ?? 2
    ;(byLayer[layer] ??= []).push(n)
  }

  const nodes: Node[] = []
  const layerHeight = 200

  for (const [layerStr, items] of Object.entries(byLayer)) {
    const layer = Number(layerStr)
    const cols = items.length
    const colWidth = Math.max(180, Math.min(240, 1400 / Math.max(cols, 1)))

    items.forEach((n, i) => {
      nodes.push({
        id: n.id,
        type: 'entity',
        position: {
          x: (i - (cols - 1) / 2) * colWidth + 700,
          y: layer * layerHeight + 60,
        },
        data: {
          label: n.name,
          entity_type: n.entity_type,
          ticker: n.ticker,
          fact_count: n.fact_count,
        },
      })
    })
  }
  return nodes
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
}

export default function SupplyChainGraph({ graphData, onNodeClick, onEdgeClick }: SupplyChainGraphProps) {
  const initialNodes = useMemo(() => layoutNodes(graphData.nodes), [graphData.nodes])
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
          <p className="text-gray-300 text-xs mt-1">请先摄取 SEC 文件或手动添加实体</p>
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
