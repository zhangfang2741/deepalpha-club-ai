'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import dynamic from 'next/dynamic'
import {
  Network, RefreshCw, Filter, AlertTriangle, BookOpen,
  TrendingDown, Plus, Loader2, X, ExternalLink,
} from 'lucide-react'

import DashboardShell from '@/components/layout/DashboardShell'
import GraphLegend, { EntityTypeBadge, RelationBadge, ENTITY_BG } from '@/components/graph/GraphLegend'
import IngestPanel from '@/components/graph/IngestPanel'
import {
  supplyChainApi,
  type EntityType,
  type RelationType,
  type GraphData,
  type GraphStats,
  type BottleneckReport,
  type Fact,
  type Entity,
} from '@/lib/api/supply_chain'

// SSR 关闭（React Flow 需要 DOM）
const SupplyChainGraph = dynamic(
  () => import('@/components/graph/SupplyChainGraph'),
  { ssr: false, loading: () => <div className="flex-1 flex items-center justify-center"><Loader2 className="w-6 h-6 animate-spin text-gray-300" /></div> },
)

const ENTITY_TYPES: EntityType[] = ['Company', 'Product', 'Technology', 'Concept', 'Resource']
const RELATION_TYPES: RelationType[] = ['HAS_PRODUCT', 'SUPPLIED_BY', 'ENABLED_BY', 'CONSTRAINED_BY']

type Tab = 'graph' | 'bottleneck' | 'ingest' | 'facts'

export default function SupplyChainPage() {
  const [activeTab, setActiveTab] = useState<Tab>('graph')
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], edges: [], total_entities: 0, total_facts: 0 })
  const [stats, setStats] = useState<GraphStats | null>(null)
  const [bottlenecks, setBottlenecks] = useState<BottleneckReport[]>([])
  const [selectedEntityFacts, setSelectedEntityFacts] = useState<Fact[]>([])
  const [selectedEntityName, setSelectedEntityName] = useState<string | null>(null)
  const [selectedEdgeEvidence, setSelectedEdgeEvidence] = useState<{ evidence: string; docUrl?: string | null } | null>(null)

  // 过滤条件
  const [filterTypes, setFilterTypes] = useState<Set<EntityType>>(new Set())
  const [filterRelations, setFilterRelations] = useState<Set<RelationType>>(new Set())
  const [filterTicker, setFilterTicker] = useState('')
  const [minConfidence, setMinConfidence] = useState(0)

  const [loading, setLoading] = useState(false)
  const [loadingBn, setLoadingBn] = useState(false)

  const fetchGraph = useCallback(async () => {
    setLoading(true)
    try {
      const data = await supplyChainApi.getGraph({
        entity_types: filterTypes.size > 0 ? [...filterTypes].join(',') : undefined,
        relation_types: filterRelations.size > 0 ? [...filterRelations].join(',') : undefined,
        ticker: filterTicker || undefined,
        min_confidence: minConfidence,
        limit: 300,
      })
      setGraphData(data)
    } catch {
      /* 后端未部署时不报错 */
    } finally {
      setLoading(false)
    }
  }, [filterTypes, filterRelations, filterTicker, minConfidence])

  const fetchStats = useCallback(async () => {
    try {
      const s = await supplyChainApi.getStats()
      setStats(s)
    } catch {
      /* ignore */
    }
  }, [])

  const fetchBottlenecks = useCallback(async () => {
    setLoadingBn(true)
    try {
      const bn = await supplyChainApi.getBottlenecks()
      setBottlenecks(bn)
    } catch {
      /* ignore */
    } finally {
      setLoadingBn(false)
    }
  }, [])

  useEffect(() => {
    fetchGraph()
    fetchStats()
  }, [fetchGraph, fetchStats])

  useEffect(() => {
    if (activeTab === 'bottleneck') fetchBottlenecks()
  }, [activeTab, fetchBottlenecks])

  const handleNodeClick = useCallback(async (nodeId: string) => {
    try {
      const facts = await supplyChainApi.getEntityFacts(nodeId, 'both')
      const node = graphData.nodes.find((n) => n.id === nodeId)
      setSelectedEntityName(node?.name ?? nodeId)
      setSelectedEntityFacts(facts)
      setSelectedEdgeEvidence(null)
    } catch {
      /* ignore */
    }
  }, [graphData.nodes])

  const handleEdgeClick = useCallback((_edgeId: string, evidence: string, docUrl?: string | null) => {
    setSelectedEdgeEvidence({ evidence, docUrl })
    setSelectedEntityFacts([])
    setSelectedEntityName(null)
  }, [])

  const toggleEntityType = (t: EntityType) => {
    setFilterTypes((prev) => {
      const next = new Set(prev)
      next.has(t) ? next.delete(t) : next.add(t)
      return next
    })
  }

  const toggleRelation = (r: RelationType) => {
    setFilterRelations((prev) => {
      const next = new Set(prev)
      next.has(r) ? next.delete(r) : next.add(r)
      return next
    })
  }

  return (
    <DashboardShell>
      {/* ── 标题栏 ───────────────────────────── */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-blue-600 rounded-xl flex items-center justify-center shadow-sm">
            <Network className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">NVIDIA 产业因果图谱</h1>
            <p className="text-xs text-gray-500">
              {stats ? `${stats.total_entities} 个实体 · ${stats.total_facts} 条事实` : '加载中…'}
            </p>
          </div>
        </div>
        <button
          onClick={() => { fetchGraph(); fetchStats() }}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          刷新
        </button>
      </div>

      {/* ── Tab 导航 ─────────────────────────── */}
      <div className="flex gap-1 mb-4 border-b border-gray-200">
        {([
          { key: 'graph', label: '图谱视图', icon: Network },
          { key: 'bottleneck', label: '瓶颈分析', icon: TrendingDown },
          { key: 'ingest', label: '摄取文档', icon: BookOpen },
          { key: 'facts', label: '事实列表', icon: Filter },
        ] as { key: Tab; label: string; icon: React.ElementType }[]).map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === key
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>

      {/* ── 内容区 ───────────────────────────── */}
      {activeTab === 'graph' && (
        <div className="grid grid-cols-[1fr_280px] gap-4 h-[calc(100vh-240px)]">
          {/* 图谱主区 */}
          <div className="flex flex-col gap-3 min-h-0">
            {/* 过滤控件 */}
            <div className="bg-white rounded-xl border border-gray-200 p-3 flex-shrink-0">
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-1.5">
                  <Filter className="w-3.5 h-3.5 text-gray-400" />
                  <span className="text-xs font-medium text-gray-500">实体类型：</span>
                  {ENTITY_TYPES.map((t) => (
                    <button
                      key={t}
                      onClick={() => toggleEntityType(t)}
                      className={`px-2 py-0.5 rounded text-xs font-medium border transition-colors ${
                        filterTypes.has(t) ? ENTITY_BG[t] : 'bg-gray-50 text-gray-400 border-gray-200'
                      }`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-gray-500">关系：</span>
                  {RELATION_TYPES.map((r) => (
                    <button
                      key={r}
                      onClick={() => toggleRelation(r)}
                      className={`px-2 py-0.5 rounded text-xs font-medium border transition-colors ${
                        filterRelations.has(r)
                          ? 'bg-gray-800 text-white border-gray-700'
                          : 'bg-gray-50 text-gray-400 border-gray-200'
                      }`}
                    >
                      {r.replace('_', ' ')}
                    </button>
                  ))}
                </div>
                <input
                  type="text"
                  placeholder="代码筛选 NVDA"
                  value={filterTicker}
                  onChange={(e) => setFilterTicker(e.target.value.toUpperCase())}
                  className="w-28 text-xs border border-gray-200 rounded-lg px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                <button
                  onClick={fetchGraph}
                  disabled={loading}
                  className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded-lg transition-colors disabled:opacity-50"
                >
                  应用
                </button>
              </div>
            </div>

            {/* 图谱画布 */}
            <div className="flex-1 bg-white rounded-xl border border-gray-200 overflow-hidden min-h-0">
              <SupplyChainGraph
                graphData={graphData}
                onNodeClick={handleNodeClick}
                onEdgeClick={handleEdgeClick}
              />
            </div>

            {/* 边证据弹出 */}
            {selectedEdgeEvidence && (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 flex-shrink-0">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1">
                    <p className="text-xs font-semibold text-amber-800 mb-1">原文证据</p>
                    <p className="text-xs text-amber-700 leading-relaxed">{selectedEdgeEvidence.evidence}</p>
                    {selectedEdgeEvidence.docUrl && (
                      <a
                        href={selectedEdgeEvidence.docUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 mt-1.5 text-xs text-blue-600 hover:underline"
                      >
                        <ExternalLink className="w-3 h-3" />
                        查看来源文档
                      </a>
                    )}
                  </div>
                  <button
                    onClick={() => setSelectedEdgeEvidence(null)}
                    className="p-1 text-amber-400 hover:text-amber-600 flex-shrink-0"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* 右侧栏 */}
          <div className="flex flex-col gap-3 overflow-y-auto">
            <GraphLegend />

            {/* 统计卡片 */}
            {stats && (
              <div className="bg-white rounded-xl border border-gray-200 p-4">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">实体分布</p>
                <div className="space-y-2">
                  {(Object.entries(stats.entities) as [EntityType, number][]).map(([type, count]) => (
                    <div key={type} className="flex items-center justify-between">
                      <EntityTypeBadge type={type} />
                      <span className="text-xs font-medium text-gray-700">{count}</span>
                    </div>
                  ))}
                </div>
                <div className="mt-3 pt-3 border-t border-gray-100">
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">事实分布</p>
                  <div className="space-y-1.5">
                    {(Object.entries(stats.facts) as [RelationType, number][]).map(([type, count]) => (
                      <div key={type} className="flex items-center justify-between">
                        <RelationBadge type={type} />
                        <span className="text-xs font-medium text-gray-700">{count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* 节点关联事实 */}
            {selectedEntityName && selectedEntityFacts.length > 0 && (
              <div className="bg-white rounded-xl border border-gray-200 p-4">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs font-semibold text-gray-800 truncate max-w-[160px]">{selectedEntityName}</p>
                  <button onClick={() => { setSelectedEntityFacts([]); setSelectedEntityName(null) }}>
                    <X className="w-3.5 h-3.5 text-gray-400" />
                  </button>
                </div>
                <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                  {selectedEntityFacts.map((f) => (
                    <div key={f.id} className="text-xs border border-gray-100 rounded-lg p-2 hover:bg-gray-50">
                      <div className="flex items-center gap-1 mb-1">
                        <span className="text-gray-500 truncate max-w-[60px]">{f.source_entity_name}</span>
                        <RelationBadge type={f.relation_type} />
                        <span className="text-gray-500 truncate max-w-[60px]">{f.target_entity_name}</span>
                      </div>
                      <p className="text-gray-400 leading-relaxed line-clamp-2">{f.evidence_text}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-gray-300">置信度 {Math.round(f.confidence * 100)}%</span>
                        {f.event_time && (
                          <span className="text-gray-300">{f.event_time.slice(0, 10)}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'bottleneck' && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-500" />
            <p className="text-sm font-medium text-gray-700">识别产业瓶颈 — 被多个产品/概念 CONSTRAINED_BY 的资源或技术</p>
          </div>

          {loadingBn ? (
            <div className="flex justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-gray-300" />
            </div>
          ) : bottlenecks.length === 0 ? (
            <div className="text-center py-16 text-gray-400 text-sm">
              暂无瓶颈数据，请先摄取相关文档
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {bottlenecks.map((bn) => (
                <div key={bn.resource_name} className="bg-white rounded-xl border border-red-100 p-4">
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <p className="text-sm font-semibold text-gray-900">{bn.resource_name}</p>
                      <EntityTypeBadge type={bn.resource_type} />
                    </div>
                    <div className="text-right">
                      <p className="text-2xl font-bold text-red-600">{bn.constrained_count}</p>
                      <p className="text-xs text-gray-400">受约束实体</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-1 mb-3">
                    {bn.constrained_entities.slice(0, 5).map((e) => (
                      <span key={e.id} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
                        {e.name}
                      </span>
                    ))}
                    {bn.constrained_entities.length > 5 && (
                      <span className="text-xs text-gray-400">+{bn.constrained_entities.length - 5}</span>
                    )}
                  </div>
                  <div className="space-y-1.5">
                    {bn.evidence_samples.map((ev, i) => (
                      <p key={i} className="text-xs text-gray-500 bg-gray-50 rounded px-2 py-1.5 line-clamp-2">
                        "{ev}"
                      </p>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'ingest' && (
        <div className="max-w-xl">
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-4">
              <BookOpen className="w-4 h-4 text-blue-600" />
              <h2 className="text-sm font-semibold text-gray-800">提交新文档</h2>
            </div>
            <p className="text-xs text-gray-500 mb-4">
              提交 SEC EDGAR 文档或电话会议记录 URL，系统将自动抓取、切片，并通过 LLM 抽取供应链事实三元组。
            </p>
            <IngestPanel onSuccess={() => { fetchGraph(); fetchStats() }} />
          </div>

          <div className="mt-4 bg-blue-50 rounded-xl border border-blue-100 p-4">
            <p className="text-xs font-semibold text-blue-800 mb-2">优先摄取建议</p>
            <div className="space-y-1.5 text-xs text-blue-700">
              <p>• NVIDIA 10-K / 10-Q — 供需紧张、产品路线图、竞争风险</p>
              <p>• TSMC 电话会议 — CoWoS 产能、HBM 供应节奏</p>
              <p>• SK Hynix / Micron 10-K — HBM3E 技术成熟度</p>
              <p>• Microsoft / Meta 8-K — 数据中心资本支出、AI 需求信号</p>
              <p>• Vertiv 投资者日资料 — 电力基础设施约束</p>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'facts' && (
        <FactsTable />
      )}
    </DashboardShell>
  )
}

function FactsTable() {
  const [facts, setFacts] = useState<Fact[]>([])
  const [loading, setLoading] = useState(false)
  const [relFilter, setRelFilter] = useState<RelationType | ''>('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await supplyChainApi.getFacts({
        relation_type: relFilter || undefined,
        limit: 200,
      })
      setFacts(data)
    } catch {
      /* ignore */
    } finally {
      setLoading(false)
    }
  }, [relFilter])

  useEffect(() => { load() }, [load])

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <select
          value={relFilter}
          onChange={(e) => setRelFilter(e.target.value as RelationType | '')}
          className="text-xs border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          <option value="">所有关系类型</option>
          {RELATION_TYPES.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-1 px-3 py-1.5 text-xs border border-gray-200 rounded-lg hover:bg-gray-50"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          刷新
        </button>
        <span className="text-xs text-gray-400">{facts.length} 条</span>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-gray-500 w-[22%]">来源实体</th>
              <th className="px-3 py-2 text-left font-medium text-gray-500 w-[16%]">关系</th>
              <th className="px-3 py-2 text-left font-medium text-gray-500 w-[22%]">目标实体</th>
              <th className="px-3 py-2 text-left font-medium text-gray-500">原文证据</th>
              <th className="px-3 py-2 text-left font-medium text-gray-500 w-[8%]">置信度</th>
              <th className="px-3 py-2 text-left font-medium text-gray-500 w-[10%]">事实时间</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading ? (
              <tr>
                <td colSpan={6} className="text-center py-8 text-gray-300">
                  <Loader2 className="w-4 h-4 animate-spin inline" />
                </td>
              </tr>
            ) : facts.length === 0 ? (
              <tr>
                <td colSpan={6} className="text-center py-8 text-gray-400">暂无数据</td>
              </tr>
            ) : facts.map((f) => (
              <tr key={f.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-3 py-2">
                  <div>
                    <p className="font-medium text-gray-800 truncate max-w-[140px]">{f.source_entity_name}</p>
                    {f.source_entity_type && <EntityTypeBadge type={f.source_entity_type} />}
                  </div>
                </td>
                <td className="px-3 py-2">
                  <RelationBadge type={f.relation_type} />
                </td>
                <td className="px-3 py-2">
                  <div>
                    <p className="font-medium text-gray-800 truncate max-w-[140px]">{f.target_entity_name}</p>
                    {f.target_entity_type && <EntityTypeBadge type={f.target_entity_type} />}
                  </div>
                </td>
                <td className="px-3 py-2">
                  <p className="text-gray-500 line-clamp-2 leading-relaxed">{f.evidence_text}</p>
                  {f.document_url && (
                    <a
                      href={f.document_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-0.5 text-blue-500 hover:underline mt-0.5"
                    >
                      <ExternalLink className="w-2.5 h-2.5" />
                      来源
                    </a>
                  )}
                </td>
                <td className="px-3 py-2 text-gray-500">{Math.round(f.confidence * 100)}%</td>
                <td className="px-3 py-2 text-gray-400">{f.event_time?.slice(0, 10) ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
