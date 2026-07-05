'use client'

/* eslint-disable react-hooks/set-state-in-effect */

import { useCallback, useEffect, useState, type ElementType } from 'react'
import dynamic from 'next/dynamic'
import {
  Network, RefreshCw, Filter, AlertTriangle,
  Loader2, X, ExternalLink, Info,
  GitBranch, Search, ArrowRight, Target, Building2, CircleGauge, Zap,
} from 'lucide-react'

import DashboardShell from '@/components/layout/DashboardShell'
import GraphLegend, { EntityTypeBadge, RelationBadge, ENTITY_BG } from '@/components/graph/GraphLegend'
import {
  supplyChainApi,
  type EntityType,
  type RelationType,
  type GraphData,
  type GraphStats,
  type BottleneckReport,
  type Fact,
  type Entity,
  type DemandChain,
  type IndustryGraphOverview,
  type OverviewItem,
} from '@/lib/api/supply_chain'

// SSR 关闭（React Flow 需要 DOM）
const SupplyChainGraph = dynamic(
  () => import('@/components/graph/SupplyChainGraph'),
  { ssr: false, loading: () => <div className="flex-1 flex items-center justify-center"><Loader2 className="w-6 h-6 animate-spin text-gray-300" /></div> },
)

const ENTITY_TYPES: EntityType[] = ['Company', 'Product', 'Technology', 'Concept', 'Resource']
const RELATION_TYPES: RelationType[] = ['HAS_PRODUCT', 'SUPPLIED_BY', 'ENABLED_BY', 'CONSTRAINED_BY']

type Tab = 'overview' | 'graph' | 'insights'

const STEPS: { key: Tab; label: string; icon: ElementType; desc: string }[] = [
  {
    key: 'overview', label: '自动研究', icon: Target,
    desc: '输入股票代码，自动排队抓取披露材料，并生成可读的投资摘要。',
  },
  {
    key: 'graph', label: '产业图谱', icon: Network,
    desc: '查看公司、产品、技术、供应商和瓶颈之间的关系；点击节点或连线看证据。',
  },
  {
    key: 'insights', label: '链路与瓶颈', icon: GitBranch,
    desc: '输入 HBM、CoWoS、AI Training 这类主题，追到产品、供应商和约束资源。',
  },
]

// 把时间范围选项换算为 since 日期（ISO，YYYY-MM-DD）；'all' 返回 undefined。
function sinceFromRange(range: 'all' | '3m' | '1y' | '2y'): string | undefined {
  if (range === 'all') return undefined
  const d = new Date()
  if (range === '3m') d.setMonth(d.getMonth() - 3)
  else if (range === '1y') d.setFullYear(d.getFullYear() - 1)
  else d.setFullYear(d.getFullYear() - 2)
  return d.toISOString().slice(0, 10)
}

export default function SupplyChainPage() {
  const [activeTab, setActiveTab] = useState<Tab>('overview')
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], edges: [], total_entities: 0, total_facts: 0 })
  const [stats, setStats] = useState<GraphStats | null>(null)
  const [overview, setOverview] = useState<IndustryGraphOverview | null>(null)
  const [bottlenecks, setBottlenecks] = useState<BottleneckReport[]>([])
  const [selectedEntityFacts, setSelectedEntityFacts] = useState<Fact[]>([])
  const [selectedEntityName, setSelectedEntityName] = useState<string | null>(null)
  const [selectedEdgeEvidence, setSelectedEdgeEvidence] = useState<{ evidence: string; docUrl?: string | null } | null>(null)

  // 过滤条件
  const [filterTypes, setFilterTypes] = useState<Set<EntityType>>(new Set())
  const [filterRelations, setFilterRelations] = useState<Set<RelationType>>(new Set())
  const [filterTicker, setFilterTicker] = useState('')
  const [minConfidence, setMinConfidence] = useState(0)
  const [timeRange, setTimeRange] = useState<'all' | '3m' | '1y' | '2y'>('all')

  const [loading, setLoading] = useState(false)
  const [loadingOverview, setLoadingOverview] = useState(false)
  const [loadingBn, setLoadingBn] = useState(false)

  // 有事实但没有任何来源文档 → 说明当前只是内置演示数据（种子不创建 SourceDocument）
  const isDemoData = !!stats && stats.total_facts > 0 && stats.documents.total === 0

  const fetchGraph = useCallback(async () => {
    setLoading(true)
    try {
      const data = await supplyChainApi.getGraph({
        entity_types: filterTypes.size > 0 ? [...filterTypes].join(',') : undefined,
        relation_types: filterRelations.size > 0 ? [...filterRelations].join(',') : undefined,
        ticker: filterTicker || undefined,
        min_confidence: minConfidence,
        since: sinceFromRange(timeRange),
        limit: 300,
      })
      setGraphData(data)
    } catch {
      /* 后端未部署时不报错 */
    } finally {
      setLoading(false)
    }
  }, [filterTypes, filterRelations, filterTicker, minConfidence, timeRange])

  const fetchStats = useCallback(async () => {
    try {
      const s = await supplyChainApi.getStats()
      setStats(s)
    } catch {
      /* ignore */
    }
  }, [])

  const fetchOverview = useCallback(async () => {
    setLoadingOverview(true)
    try {
      const data = await supplyChainApi.getOverview({
        ticker: filterTicker || undefined,
        min_confidence: minConfidence,
        since: sinceFromRange(timeRange),
        limit: 300,
      })
      setOverview(data)
    } catch {
      setOverview(null)
    } finally {
      setLoadingOverview(false)
    }
  }, [filterTicker, minConfidence, timeRange])

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
    fetchOverview()
  }, [fetchGraph, fetchStats, fetchOverview])

  useEffect(() => {
    if (activeTab === 'insights') fetchBottlenecks()
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
      if (next.has(t)) next.delete(t)
      else next.add(t)
      return next
    })
  }

  const toggleRelation = (r: RelationType) => {
    setFilterRelations((prev) => {
      const next = new Set(prev)
      if (next.has(r)) next.delete(r)
      else next.add(r)
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
            <h1 className="text-xl font-bold text-gray-900">
              {filterTicker ? `${filterTicker} 产业链图谱` : '产业因果图谱'}
            </h1>
            <p className="text-xs text-gray-500">
              {stats ? `${stats.total_entities} 个实体 · ${stats.total_facts} 条事实` : '加载中…'}
            </p>
          </div>
        </div>
        <button
          onClick={() => { fetchGraph(); fetchStats(); fetchOverview() }}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          刷新
        </button>
      </div>

      {/* ── 流程步骤导航 ─────────────────────────── */}
      <div className="mb-4">
        <div className="inline-flex max-w-full items-center gap-1 overflow-x-auto rounded-xl border border-gray-200 bg-white p-1">
          {STEPS.map(({ key, label, icon: Icon }) => {
            const active = activeTab === key
            return (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                className={`flex items-center gap-2 rounded-lg px-3 py-2 whitespace-nowrap transition-colors ${
                  active
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'text-gray-500 hover:bg-gray-50 hover:text-gray-800'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span className="text-sm font-medium">{label}</span>
              </button>
            )
          })}
        </div>

        {/* 当前步骤说明 */}
        <div className="mt-2 rounded-lg bg-gray-50 border border-gray-100 px-3 py-2">
          <span className="text-xs text-gray-600 leading-relaxed">
            {STEPS.find((s) => s.key === activeTab)?.desc}
          </span>
        </div>
      </div>

      {/* ── 演示数据提示 ─────────────────────────── */}
      {/* 仅有内置演示数据（有事实但无任何来源文档）时提示，避免投资者误把示例当可溯源结论 */}
      {isDemoData && (
        <div className="mb-4 flex items-start gap-2 rounded-xl bg-amber-50 border border-amber-200 px-3 py-2.5">
          <Info className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
          <div className="text-xs text-amber-800 leading-relaxed">
            <span className="font-semibold">当前为内置 NVIDIA 演示数据</span>
            ，用于体验功能，<span className="font-semibold">非实时抽取、无原始文档来源，请勿作为投资依据</span>。
            输入股票代码启动自动研究后，会逐步替换为可溯源的真实材料。
          </div>
        </div>
      )}

      {/* ── 内容区 ───────────────────────────── */}
      {activeTab === 'overview' && (
        <OverviewPanel
          overview={overview}
          loading={loadingOverview}
          focusTicker={filterTicker}
          setFocusTicker={setFilterTicker}
          setOverview={setOverview}
          onRefresh={fetchOverview}
          onRefreshAll={() => { fetchGraph(); fetchStats(); fetchOverview() }}
          onOpenGraph={() => setActiveTab('graph')}
          onOpenInsights={() => setActiveTab('insights')}
        />
      )}

      {activeTab === 'graph' && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 lg:h-[calc(100vh-240px)]">
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
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-gray-500">聚焦公司</span>
                  <input
                    type="text"
                    placeholder="留空看全部"
                    value={filterTicker}
                    onChange={(e) => setFilterTicker(e.target.value.toUpperCase())}
                    className="w-28 text-xs border border-gray-200 rounded-lg px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>
                {/* 时间范围（按事实发生时间） */}
                <select
                  value={timeRange}
                  onChange={(e) => setTimeRange(e.target.value as 'all' | '3m' | '1y' | '2y')}
                  className="text-xs border border-gray-200 rounded-lg px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  <option value="all">全部时间</option>
                  <option value="3m">近 3 个月</option>
                  <option value="1y">近 1 年</option>
                  <option value="2y">近 2 年</option>
                </select>
                {/* 置信度下限 */}
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-gray-500">置信度≥</span>
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.05}
                    value={minConfidence}
                    onChange={(e) => setMinConfidence(Number(e.target.value))}
                    className="w-20 accent-blue-600"
                  />
                  <span className="text-xs text-gray-600 w-8">{Math.round(minConfidence * 100)}%</span>
                </div>
                <button
                  onClick={fetchGraph}
                  disabled={loading}
                  className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded-lg transition-colors disabled:opacity-50"
                >
                  应用
                </button>
              </div>
            </div>

            {/* 图谱画布（移动端给固定高度，桌面端填满列高） */}
            <div className="h-[60vh] lg:h-auto lg:flex-1 bg-white rounded-xl border border-gray-200 overflow-hidden min-h-0">
              <SupplyChainGraph
                graphData={graphData}
                onNodeClick={handleNodeClick}
                onEdgeClick={handleEdgeClick}
                onIngestClick={() => setActiveTab('overview')}
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

      {activeTab === 'insights' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 xl:grid-cols-[420px_1fr] gap-4">
            <DemandChainPanel />
            <div className="flex items-center gap-2 rounded-xl border border-gray-200 bg-white p-4">
              <AlertTriangle className="w-4 h-4 text-red-500" />
              <p className="text-sm font-medium text-gray-700">下方是当前图谱识别出的核心瓶颈。</p>
            </div>
          </div>

          {loadingBn ? (
            <div className="flex justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-gray-300" />
            </div>
          ) : bottlenecks.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-16">
              <p className="text-gray-400 text-sm">暂无瓶颈数据</p>
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
                  {/* 中文解读 */}
                  {bn.description && (
                    <p className="text-xs text-gray-700 leading-relaxed bg-red-50 rounded-lg px-2.5 py-2 mb-3">
                      {bn.description}
                    </p>
                  )}

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
                  {bn.evidence_samples.length > 0 && (
                    <div className="space-y-1.5">
                      <p className="text-[11px] font-medium text-gray-400">原文证据</p>
                      {bn.evidence_samples.map((ev, i) => (
                        <p key={i} className="text-xs text-gray-500 bg-gray-50 rounded px-2 py-1.5 line-clamp-2">
                          “{ev}”
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </DashboardShell>
  )
}

function OverviewMetric({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl px-4 py-3">
      <p className="text-xs text-gray-400">{label}</p>
      <p className="mt-1 text-2xl font-bold text-gray-900">{value}</p>
      <p className="mt-1 text-xs text-gray-500">{hint}</p>
    </div>
  )
}

function OverviewSection({
  title,
  icon: Icon,
  items,
  empty,
}: {
  title: string
  icon: ElementType
  items: OverviewItem[]
  empty: string
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Icon className="w-4 h-4 text-blue-600" />
        <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-gray-400 py-6 text-center">{empty}</p>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <div key={`${title}-${item.title}`} className="border border-gray-100 rounded-lg p-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-gray-800">{item.title}</p>
                  <p className="mt-1 text-xs text-gray-500 leading-relaxed">{item.description}</p>
                </div>
                <span className="flex-shrink-0 text-xs font-semibold text-blue-700 bg-blue-50 border border-blue-100 rounded px-2 py-1">
                  {Math.round(item.score * 100)}
                </span>
              </div>
              {item.entities.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {item.entities.slice(0, 6).map((entity) => (
                    <span key={entity.id} className="inline-flex items-center gap-1 text-xs bg-gray-50 border border-gray-200 rounded px-2 py-0.5 text-gray-600">
                      {entity.name}
                    </span>
                  ))}
                </div>
              )}
              {item.evidence_samples.length > 0 && (
                <p className="mt-2 text-xs text-gray-400 line-clamp-2">
                  “{item.evidence_samples[0]}”
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function OverviewPanel({
  overview,
  loading,
  focusTicker,
  setFocusTicker,
  setOverview,
  onRefresh,
  onRefreshAll,
  onOpenGraph,
  onOpenInsights,
}: {
  overview: IndustryGraphOverview | null
  loading: boolean
  focusTicker: string
  setFocusTicker: (value: string) => void
  setOverview: (value: IndustryGraphOverview | null) => void
  onRefresh: () => void
  onRefreshAll: () => void
  onOpenGraph: () => void
  onOpenInsights: () => void
}) {
  if (loading && !overview) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-gray-300" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <AutoResearchPanel
        onStarted={(tickers, nextOverview) => {
          setFocusTicker(tickers[0] ?? '')
          if (nextOverview) setOverview(nextOverview)
          onRefreshAll()
        }}
      />

      <div className="bg-white border border-gray-200 rounded-xl p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Target className="w-4 h-4 text-blue-600" />
              <h2 className="text-lg font-bold text-gray-900">{overview?.title ?? '产业图谱总览'}</h2>
              {overview?.data_mode === 'demo' && (
                <span className="text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-0.5">
                  演示数据
                </span>
              )}
            </div>
            <p className="mt-2 text-sm text-gray-600 leading-relaxed max-w-4xl">
              {overview?.summary ?? '暂无可用摘要。可以先使用内置演示数据，或摄取目标公司的公开披露材料。'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <input
              value={focusTicker}
              onChange={(e) => setFocusTicker(e.target.value.toUpperCase())}
              onKeyDown={(e) => { if (e.key === 'Enter') onRefresh() }}
              placeholder="聚焦股票"
              className="w-28 text-xs border border-gray-200 rounded-lg px-2 py-2 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <button
              onClick={onRefresh}
              disabled={loading}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              更新
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <OverviewMetric label="实体规模" value={`${overview?.total_entities ?? 0}`} hint="公司、产品、技术、概念、资源" />
        <OverviewMetric label="事实数量" value={`${overview?.total_facts ?? 0}`} hint="可点击核对的关系证据" />
        <OverviewMetric label="平均置信度" value={`${Math.round((overview?.confidence ?? 0) * 100)}%`} hint="来自抽取事实的均值" />
        <OverviewMetric
          label="数据状态"
          value={overview?.data_mode === 'documented' ? '可溯源' : overview?.data_mode === 'demo' ? '演示' : '空'}
          hint="真实文档优先于演示数据"
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <OverviewSection title="关键公司" icon={Building2} items={overview?.key_companies ?? []} empty="暂无关键公司" />
        <OverviewSection title="核心瓶颈" icon={AlertTriangle} items={overview?.bottlenecks ?? []} empty="暂无瓶颈关系" />
        <OverviewSection title="需求链路" icon={GitBranch} items={overview?.demand_chains ?? []} empty="暂无需求概念" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <CircleGauge className="w-4 h-4 text-blue-600" />
            <h3 className="text-sm font-semibold text-gray-900">需要继续验证的问题</h3>
          </div>
          <div className="space-y-2">
            {(overview?.investor_questions ?? []).map((question) => (
              <p key={question} className="text-xs text-gray-600 leading-relaxed border-l-2 border-blue-100 pl-2">
                {question}
              </p>
            ))}
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-900">下一步动作</h3>
          </div>
          <div className="space-y-2">
            {(overview?.next_actions ?? []).map((action) => (
              <p key={action} className="text-xs text-gray-600 leading-relaxed">
                {action}
              </p>
            ))}
          </div>
          <div className="flex flex-wrap gap-2 mt-4">
            <button onClick={onOpenGraph} className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded-lg hover:bg-blue-700">
              <Network className="w-3.5 h-3.5" />
              查看图谱
            </button>
            <button onClick={onOpenInsights} className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-gray-200 text-gray-600 text-xs font-medium rounded-lg hover:bg-gray-50">
              <GitBranch className="w-3.5 h-3.5" />
              追链路
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

const AUTO_SEC_FORMS = ['10-K', '10-Q', '8-K']

function parseTickerInput(input: string): string[] {
  const aliases: Record<string, string> = {
    APPLE: 'AAPL',
    TESLA: 'TSLA',
    NVIDIA: 'NVDA',
  }
  const seen = new Set<string>()
  return input
    .split(/[\s,，;；]+/)
    .map((token) => aliases[token.trim().toUpperCase()] ?? token.trim().toUpperCase())
    .filter(Boolean)
    .filter((token) => {
      if (seen.has(token)) return false
      seen.add(token)
      return true
    })
}

function AutoResearchPanel({
  onStarted,
}: {
  onStarted: (tickers: string[], overview: IndustryGraphOverview | null) => void
}) {
  const [tickerText, setTickerText] = useState('NVDA TSLA AAPL')
  const [secForms, setSecForms] = useState<Set<string>>(new Set(['10-K', '10-Q']))
  const [includeEarnings, setIncludeEarnings] = useState(true)
  const [recentQuarters, setRecentQuarters] = useState(1)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; message: string; tasks: string[] } | null>(null)

  const tickers = parseTickerInput(tickerText)
  const taskCount = tickers.length * (secForms.size + (includeEarnings ? recentQuarters : 0))

  const toggleForm = (form: string) => {
    setSecForms((prev) => {
      const next = new Set(prev)
      if (next.has(form)) next.delete(form)
      else next.add(form)
      return next
    })
  }

  const run = async () => {
    if (tickers.length === 0 || taskCount === 0) return
    setLoading(true)
    setResult(null)
    try {
      const data = await supplyChainApi.runAutomation({
        tickers,
        sec_forms: [...secForms],
        include_earnings: includeEarnings,
        recent_quarters: includeEarnings ? recentQuarters : 0,
      })
      setResult({
        ok: true,
        message: data.message,
        tasks: data.queued_tasks.map((task) => task.label),
      })
      onStarted(data.tickers, data.overview)
    } catch (e) {
      setResult({
        ok: false,
        message: e instanceof Error ? e.message : '自动研究启动失败',
        tasks: [],
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-white border border-blue-100 rounded-xl p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-blue-600" />
            <h3 className="text-sm font-semibold text-gray-900">自动研究入口</h3>
            <span className="text-xs text-gray-400">常规使用只需要这里</span>
          </div>
          <input
            value={tickerText}
            onChange={(e) => setTickerText(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') run() }}
            placeholder="输入股票代码，如 NVDA TSLA AAPL"
            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <div className="flex flex-wrap items-center gap-2 mt-2">
            {AUTO_SEC_FORMS.map((form) => (
              <button
                key={form}
                onClick={() => toggleForm(form)}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium border ${
                  secForms.has(form)
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-gray-50 text-gray-500 border-gray-200'
                }`}
              >
                {form}
              </button>
            ))}
            <label className="inline-flex items-center gap-1.5 text-xs text-gray-600">
              <input
                type="checkbox"
                checked={includeEarnings}
                onChange={(e) => setIncludeEarnings(e.target.checked)}
                className="accent-blue-600"
              />
              最近电话会议
            </label>
            <select
              value={recentQuarters}
              disabled={!includeEarnings}
              onChange={(e) => setRecentQuarters(Number(e.target.value))}
              className="text-xs border border-gray-200 rounded-lg px-2 py-1 disabled:bg-gray-50 disabled:text-gray-300"
            >
              {[1, 2, 3, 4].map((count) => (
                <option key={count} value={count}>近 {count} 季</option>
              ))}
            </select>
          </div>
          <p className="mt-2 text-xs text-gray-400">
            已识别：{tickers.length > 0 ? tickers.join('、') : '无'} · 将自动排队 {taskCount} 个后台任务，下面的图谱、链路和瓶颈会复用同一批结果
          </p>
        </div>
        <button
          onClick={run}
          disabled={loading || tickers.length === 0 || taskCount === 0}
          className="inline-flex items-center justify-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 text-white text-sm font-medium rounded-lg transition-colors"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
          {loading ? '启动中' : '自动生成图谱'}
        </button>
      </div>

      {result && (
        <div className={`mt-3 rounded-lg border px-3 py-2 text-xs ${result.ok ? 'bg-green-50 border-green-200 text-green-700' : 'bg-red-50 border-red-200 text-red-700'}`}>
          <p className="font-medium">{result.message}</p>
          {result.tasks.length > 0 && (
            <p className="mt-1 text-green-600/80 line-clamp-2">
              {result.tasks.slice(0, 8).join('、')}{result.tasks.length > 8 ? ` 等 ${result.tasks.length} 个任务` : ''}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ── 需求传导链路（P2：把后端 demand-chain 分析暴露到前端）──────
const DEMAND_EXAMPLES = ['HBM', 'CoWoS', 'AI Training', 'Data Center']

function ChainColumn({ title, color, entities, empty }: { title: string; color: string; entities: Entity[]; empty: string }) {
  return (
    <div className="flex-1 min-w-[150px]">
      <p className="text-xs font-semibold mb-2" style={{ color }}>{title}</p>
      <div className="space-y-1.5">
        {entities.length === 0 ? (
          <p className="text-xs text-gray-300">{empty}</p>
        ) : entities.map((e) => (
          <div key={e.id} className="bg-white border border-gray-200 rounded-lg px-2 py-1.5">
            <p className="text-xs font-medium text-gray-800 truncate">{e.name}</p>
            <EntityTypeBadge type={e.entity_type} />
          </div>
        ))}
      </div>
    </div>
  )
}

function DemandChainPanel() {
  const [concept, setConcept] = useState('')
  const [chain, setChain] = useState<DemandChain | null>(null)
  const [loading, setLoading] = useState(false)
  const [notFound, setNotFound] = useState(false)

  const run = useCallback(async (q: string) => {
    const query = q.trim()
    if (!query) return
    setLoading(true)
    setNotFound(false)
    setChain(null)
    try {
      const data = await supplyChainApi.getDemandChain(query)
      setChain(data)
    } catch {
      setNotFound(true)
    } finally {
      setLoading(false)
    }
  }, [])

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
            <input
              type="text"
              value={concept}
              onChange={(e) => setConcept(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') run(concept) }}
              placeholder="输入主题、技术或资源，如 HBM、CoWoS、AI Training…"
              className="w-full text-sm border border-gray-200 rounded-lg pl-8 pr-3 py-2 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <button
            onClick={() => run(concept)}
            disabled={loading || !concept.trim()}
            className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 text-white text-sm font-medium rounded-lg transition-colors"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <GitBranch className="w-4 h-4" />}
            追溯链路
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5 mt-2">
          <span className="text-xs text-gray-400">试试：</span>
          {DEMAND_EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => { setConcept(ex); run(ex) }}
              className="text-xs px-2 py-0.5 bg-gray-50 text-gray-600 border border-gray-200 rounded hover:border-blue-300"
            >
              {ex}
            </button>
          ))}
        </div>
      </div>

      {notFound && (
        <div className="flex flex-col items-center gap-2 py-10 text-center">
          <p className="text-sm text-gray-400">未找到该主题，或图谱中暂无相关链路数据</p>
          <p className="text-xs text-gray-400">可以先回到自动研究，输入目标股票补充基础数据。</p>
        </div>
      )}

      {chain && (
        <div className="bg-gray-50 rounded-xl border border-gray-200 p-4">
          <div className="flex items-center gap-2 mb-4">
            <span className="text-sm font-semibold text-gray-900">{chain.concept.name}</span>
            <EntityTypeBadge type={chain.concept.entity_type} />
            <span className="text-xs text-gray-400">的产业链路</span>
          </div>
          <div className="flex items-start gap-2 overflow-x-auto pb-2">
            <ChainColumn title="① 依赖产品 / 技术" color="#10B981" entities={chain.enabled_products} empty="无" />
            <ArrowRight className="w-4 h-4 text-gray-300 flex-shrink-0 mt-7" />
            <ChainColumn title="② 供应商" color="#3B82F6" entities={chain.supplier_companies} empty="无" />
            <ArrowRight className="w-4 h-4 text-gray-300 flex-shrink-0 mt-7" />
            <ChainColumn title="③ 瓶颈资源" color="#EF4444" entities={chain.constrained_resources} empty="无" />
          </div>
        </div>
      )}
    </div>
  )
}
