'use client'

/* eslint-disable react-hooks/set-state-in-effect */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle,
  ArrowRight,
  Building2,
  CalendarDays,
  ExternalLink,
  Factory,
  FileSearch,
  FileText,
  HelpCircle,
  Loader2,
  MessageSquareText,
  Network,
  Package,
  Search,
  Shield,
  Sparkles,
  TrendingUp,
  Users,
} from 'lucide-react'

import DashboardShell from '@/components/layout/DashboardShell'
import StockAnalysisCard from '@/components/analysis/StockAnalysisCard'
import { analyzeStock, type AnalysisResponse } from '@/lib/api/analysis'
import {
  fetchCompanyProfile,
  fetchCompanyFilings,
  streamCompanyProfile,
  type CompanyFilingsResponse,
  type CompanyProfile,
  type CompanyProfileResponse,
  type FilingRecord,
  type ProductItem,
} from '@/lib/api/sec_filings'
import {
  fetchTranscriptDetail,
  fetchTranscriptList,
  fetchTranscriptSummary,
  type TranscriptCandidate,
  type TranscriptDetailResponse,
  type TranscriptSummaryResponse,
} from '@/lib/api/transcripts'

type ResearchTab = 'overview' | 'sec' | 'transcripts' | 'score'

type ProfileProgress = {
  event: 'start' | 'resolved' | 'cache_hit' | 'meta' | 'generating'
  message: string
  company?: Partial<CompanyProfileResponse>
}

const TABS: { id: ResearchTab; label: string; icon: typeof Building2 }[] = [
  { id: 'overview', label: '公司概览', icon: Sparkles },
  { id: 'sec', label: 'SEC 文件', icon: FileText },
  { id: 'transcripts', label: '财报电话会', icon: MessageSquareText },
  { id: 'score', label: '投资评分', icon: TrendingUp },
]

const QUICK_TICKERS = ['NVDA', 'TSLA', 'AAPL', 'MSFT', 'AMZN', 'META', 'GOOGL', 'AMD']

const MOAT_BADGE_STYLES: Record<CompanyProfile['moat_rating'], string> = {
  宽: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  中: 'bg-blue-100 text-blue-700 border-blue-200',
  窄: 'bg-amber-100 text-amber-700 border-amber-200',
  无: 'bg-gray-100 text-gray-600 border-gray-200',
}

function normalizeTicker(value: string) {
  return value.trim().toUpperCase().replace('/', '.')
}

function getInitialCompanyResearchSymbol() {
  if (typeof window === 'undefined') return 'NVDA'
  const params = new URLSearchParams(window.location.search)
  return normalizeTicker(params.get('symbol') || params.get('ticker') || 'NVDA') || 'NVDA'
}

function isEmbeddedCompanyResearch() {
  if (typeof window === 'undefined') return false
  return new URLSearchParams(window.location.search).get('embedded') === '1'
}

function formatDate(value: string | null | undefined) {
  if (!value) return '日期未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value.slice(0, 10)
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}

function getErrorMessage(error: unknown, fallback: string) {
  const apiError = error as { response?: { data?: { detail?: unknown; error?: unknown } }; message?: string }
  if (apiError.response?.data?.error === 'Rate limit exceeded') {
    return '请求太频繁，请稍等几秒后再试'
  }
  const detail = apiError.response?.data?.detail ?? apiError.response?.data?.error
  if (typeof detail === 'string') return detail
  if (error instanceof Error) return error.message
  return fallback
}

function MoatBadge({ rating }: { rating: CompanyProfile['moat_rating'] }) {
  const cls = MOAT_BADGE_STYLES[rating] ?? MOAT_BADGE_STYLES.无
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${cls}`}>
      {rating}护城河
    </span>
  )
}

function ProductChip({ item }: { item: ProductItem }) {
  const marketShare = item.market_share?.trim()
  return (
    <span className="group relative inline-block">
      <span className="inline-flex items-center gap-1.5 rounded-lg border border-dashed border-blue-200 bg-blue-50 px-2.5 py-1 text-xs text-blue-700 transition-colors group-hover:border-blue-400 group-hover:bg-blue-100">
        {item.name}
        {marketShare && marketShare !== '未知/未披露' && (
          <span className="rounded bg-white/80 px-1.5 py-0.5 text-[10px] font-medium text-blue-600">
            {marketShare}
          </span>
        )}
        {(item.explanation || marketShare) && <HelpCircle className="h-3 w-3 text-blue-400" />}
      </span>
      {(item.explanation || marketShare) && (
        <span
          role="tooltip"
          className="pointer-events-none absolute bottom-full left-0 z-30 mb-2 w-64 rounded-xl bg-gray-900 px-3 py-2 text-xs leading-relaxed text-gray-100 opacity-0 shadow-xl transition-opacity duration-150 group-hover:opacity-100"
        >
          {item.explanation && <span>{item.explanation}</span>}
          {marketShare && <span className="mt-1.5 block text-blue-100">市占率：{marketShare}</span>}
          <span className="absolute left-5 top-full -mt-px h-2 w-2 rotate-45 bg-gray-900" />
        </span>
      )}
    </span>
  )
}

function ProfileChips({ items }: { items: string[] }) {
  const cleanItems = items.filter(Boolean)
  return (
    <div className="flex flex-wrap gap-1.5">
      {cleanItems.map((item, index) => (
        <span key={`${item}-${index}`} className="rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs text-gray-700">
          {item}
        </span>
      ))}
    </div>
  )
}

function ProfileBlock({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode
  title: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-gray-500">
        {icon}
        {title}
      </div>
      <div className="text-sm leading-relaxed text-gray-700">{children}</div>
    </div>
  )
}

function splitSupplyChainText(text: string) {
  const cleaned = text.trim()
  const upstream = cleaned.match(/上游[：:，,]?\s*([^；;。]+)/)?.[1]?.trim()
  const midstream = cleaned.match(/中游[：:，,]?\s*([^；;。]+)/)?.[1]?.trim()
  const downstream = cleaned.match(/下游[：:，,]?\s*([^；;。]+)/)?.[1]?.trim()

  return {
    upstream: upstream || '关键零部件、原材料、代工/基础设施供应方',
    midstream: midstream || cleaned,
    downstream: downstream || '终端客户、渠道、生态伙伴和最终用户',
  }
}

function FlowItems({ items }: { items: string[] }) {
  const visible = items.filter(Boolean).slice(0, 4)
  if (visible.length === 0) return null
  return (
    <div className="mt-3 flex flex-wrap gap-1.5">
      {visible.map((item, index) => (
        <span key={`${item}-${index}`} className="rounded-md bg-white/80 px-2 py-1 text-[11px] font-medium text-gray-600">
          {item}
        </span>
      ))}
    </div>
  )
}

function SupplyChainFlow({
  position,
  products,
  customers,
}: {
  position: string
  products: ProductItem[]
  customers: string[]
}) {
  const stages = splitSupplyChainText(position)
  const productNames = products.map((item) => item.name).filter(Boolean)

  const cards = [
    {
      key: 'upstream',
      label: '上游',
      title: '供应与资源',
      body: stages.upstream,
      icon: Factory,
      tone: 'border-amber-100 bg-amber-50 text-amber-700',
      items: [],
    },
    {
      key: 'company',
      label: '公司环节',
      title: '核心产品 / 平台',
      body: stages.midstream,
      icon: Building2,
      tone: 'border-blue-100 bg-blue-50 text-blue-700',
      items: productNames,
    },
    {
      key: 'downstream',
      label: '下游',
      title: '客户与应用',
      body: stages.downstream,
      icon: Users,
      tone: 'border-emerald-100 bg-emerald-50 text-emerald-700',
      items: customers,
    },
  ]

  return (
    <section className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        <Network className="h-4 w-4 text-blue-600" />
        <h2 className="text-sm font-bold text-gray-900">供应链位置</h2>
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_auto_1fr_auto_1fr] lg:items-stretch">
        {cards.map((card, index) => {
          const Icon = card.icon
          return (
            <div key={card.key} className="contents">
              <div className={`rounded-xl border p-4 ${card.tone}`}>
                <div className="flex items-center gap-2 text-xs font-bold">
                  <Icon className="h-3.5 w-3.5" />
                  {card.label}
                </div>
                <div className="mt-2 text-sm font-bold text-gray-900">{card.title}</div>
                <p className="mt-2 text-xs leading-6 text-gray-700">{card.body}</p>
                <FlowItems items={card.items} />
              </div>
              {index < cards.length - 1 && (
                <div className="flex items-center justify-center text-gray-300">
                  <ArrowRight className="hidden h-5 w-5 lg:block" />
                  <div className="h-4 w-px bg-gray-200 lg:hidden" />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}

function CompanyOverviewTab({
  ticker,
  profile,
  loading,
  progress,
  error,
  onRetry,
}: {
  ticker: string
  profile: CompanyProfile | null
  loading: boolean
  progress: ProfileProgress | null
  error: string
  onRetry: () => void
}) {
  if (!ticker) {
    return <EmptyState icon={Building2} text="输入股票代码后查看公司概览" />
  }
  if (loading) {
    const stepOrder: ProfileProgress['event'][] = ['start', 'resolved', 'meta', 'generating']
    const activeIndex = progress ? Math.max(0, stepOrder.indexOf(progress.event)) : 0
    const progressWidth = `${((activeIndex + 1) / stepOrder.length) * 100}%`
    const company = progress?.company

    return (
      <div className="min-h-[320px] rounded-2xl border border-blue-100 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
          <div>
            <div className="text-sm font-bold text-gray-900">{progress?.message || 'AI 正在生成公司概览'}</div>
            <div className="mt-1 text-xs text-gray-500">解析公司、补全 SEC 信息、生成产品/市占率/护城河判断</div>
          </div>
        </div>

        <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-gray-100">
          <div className="h-full rounded-full bg-blue-600 transition-all duration-500" style={{ width: progressWidth }} />
        </div>

        {company && (
          <div className="mt-5 grid grid-cols-1 gap-3 rounded-xl border border-gray-100 bg-gray-50 p-4 text-sm md:grid-cols-3">
            <div>
              <div className="text-xs font-semibold text-gray-400">公司</div>
              <div className="mt-1 font-semibold text-gray-900">{company.name || ticker}</div>
            </div>
            <div>
              <div className="text-xs font-semibold text-gray-400">代码 / CIK</div>
              <div className="mt-1 font-semibold text-gray-900">{company.ticker || ticker} · {company.cik || '-'}</div>
            </div>
            <div>
              <div className="text-xs font-semibold text-gray-400">SEC 行业</div>
              <div className="mt-1 font-semibold text-gray-900">{company.sic_description || '补全中'}</div>
            </div>
          </div>
        )}

        <div className="mt-5 grid grid-cols-1 gap-2 text-xs text-gray-500 md:grid-cols-4">
          {[
            ['start', '解析代码'],
            ['resolved', '识别公司'],
            ['meta', '补全行业'],
            ['generating', '生成画像'],
          ].map(([id, label], index) => (
            <div
              key={id}
              className={`rounded-lg border px-3 py-2 ${
                index <= activeIndex ? 'border-blue-100 bg-blue-50 text-blue-700' : 'border-gray-100 bg-gray-50'
              }`}
            >
              {label}
            </div>
          ))}
        </div>
      </div>
    )
  }
  if (error) {
    return <ErrorState message={error} onRetry={onRetry} />
  }
  if (!profile) {
    return <EmptyState icon={Sparkles} text="暂无公司概览" />
  }

  const mainProducts = Array.isArray(profile.main_products) ? profile.main_products : []
  const mainCustomers = Array.isArray(profile.main_customers) ? profile.main_customers : []
  const competitors = Array.isArray(profile.competitors) ? profile.competitors : []
  const moatRating = profile.moat_rating ?? '无'
  const moatText = profile.moat_reason || profile.differentiation || '暂无护城河说明'

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-blue-100 bg-gradient-to-br from-blue-50/70 to-white p-5 shadow-sm">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm font-bold text-blue-700">
            <Sparkles className="h-4 w-4" />
            AI 公司速览
          </div>
          <span className="text-[11px] text-gray-400">大模型生成，仅供参考</span>
        </div>
        {profile.one_liner && (
          <p className="text-[15px] font-medium leading-relaxed text-gray-900">{profile.one_liner}</p>
        )}
        <div className="mt-4 rounded-xl border border-gray-100 bg-white/70 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <Shield className="h-3.5 w-3.5 text-gray-500" />
            <span className="text-xs font-semibold text-gray-500">护城河判断</span>
            <MoatBadge rating={moatRating} />
          </div>
          <p className="mt-2 text-sm leading-relaxed text-gray-700">
            {moatText}
          </p>
        </div>
      </section>

      {profile.supply_chain_position && (
        <SupplyChainFlow
          position={profile.supply_chain_position}
          products={mainProducts}
          customers={mainCustomers}
        />
      )}

      <section className="grid grid-cols-1 gap-4 rounded-2xl border border-gray-100 bg-white p-5 shadow-sm md:grid-cols-2">
        {profile.industry && (
          <ProfileBlock icon={<Factory className="h-3.5 w-3.5" />} title="所属行业">
            {profile.industry}
          </ProfileBlock>
        )}
        {mainProducts.length > 0 && (
          <ProfileBlock icon={<Package className="h-3.5 w-3.5" />} title="主要产品 / 市占率">
            <div className="flex flex-wrap gap-1.5">
              {mainProducts.map((item, index) => (
                <ProductChip key={`${item.name || 'product'}-${index}`} item={item} />
              ))}
            </div>
          </ProfileBlock>
        )}
        {mainCustomers.length > 0 && (
          <ProfileBlock icon={<Users className="h-3.5 w-3.5" />} title="主要客户">
            <ProfileChips items={mainCustomers} />
          </ProfileBlock>
        )}
        {competitors.length > 0 && (
          <ProfileBlock icon={<Building2 className="h-3.5 w-3.5" />} title="主要竞争对手">
            <ProfileChips items={competitors} />
          </ProfileBlock>
        )}
        {profile.differentiation && (
          <div className="md:col-span-2">
            <ProfileBlock icon={<Shield className="h-3.5 w-3.5" />} title="核心差异化竞争力">
              {profile.differentiation}
            </ProfileBlock>
          </div>
        )}
      </section>
    </div>
  )
}

function SecFilingsTab({
  data,
  loading,
  error,
  onRetry,
}: {
  data: CompanyFilingsResponse | null
  loading: boolean
  error: string
  onRetry: () => void
}) {
  const [activeCat, setActiveCat] = useState('all')

  useEffect(() => {
    setActiveCat('all')
  }, [data?.company.cik])

  const visibleFilings: FilingRecord[] = useMemo(() => {
    if (!data) return []
    if (activeCat === 'all') return data.categories.flatMap((category) => category.filings)
    return data.categories.find((category) => category.key === activeCat)?.filings ?? []
  }, [activeCat, data])

  const sortedVisible =
    activeCat === 'all'
      ? [...visibleFilings].sort((a, b) => (a.filing_date < b.filing_date ? 1 : -1))
      : visibleFilings

  if (loading) return <LoadingState text="正在从 SEC 拉取文件..." />
  if (error) return <ErrorState message={error} onRetry={onRetry} />
  if (!data) return <EmptyState icon={FileText} text="输入股票代码后查看 SEC 文件" />

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-gray-900">{data.company.name || '未知公司'}</h2>
            <div className="mt-1.5 flex flex-wrap items-center gap-2 text-sm text-gray-500">
              {data.company.tickers.map((ticker) => (
                <span key={ticker} className="rounded bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">
                  {ticker}
                </span>
              ))}
              <span>CIK {data.company.cik}</span>
              {data.company.exchanges.length > 0 && <span>· {data.company.exchanges.join(', ')}</span>}
            </div>
            {data.company.sic_description && (
              <p className="mt-1 text-xs text-gray-400">{data.company.sic_description}</p>
            )}
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold text-blue-600 tabular-nums">{data.total.toLocaleString()}</div>
            <div className="text-xs text-gray-400">份文件</div>
          </div>
        </div>
      </section>

      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setActiveCat('all')}
          className={`rounded-full border px-3 py-1.5 text-sm font-medium transition-all ${
            activeCat === 'all'
              ? 'border-blue-600 bg-blue-600 text-white'
              : 'border-gray-200 bg-white text-gray-600 hover:border-blue-300'
          }`}
        >
          全部 <span className="opacity-70 tabular-nums">{data.total}</span>
        </button>
        {data.categories.map((category) => (
          <button
            key={category.key}
            onClick={() => setActiveCat(category.key)}
            disabled={category.count === 0}
            className={`rounded-full border px-3 py-1.5 text-sm font-medium transition-all disabled:cursor-not-allowed disabled:opacity-40 ${
              activeCat === category.key
                ? 'border-blue-600 bg-blue-600 text-white'
                : 'border-gray-200 bg-white text-gray-600 hover:border-blue-300'
            }`}
          >
            {category.label} <span className="opacity-70 tabular-nums">{category.count}</span>
          </button>
        ))}
      </div>

      <section className="rounded-2xl border border-gray-100 bg-white shadow-sm">
        {sortedVisible.length === 0 ? (
          <div className="py-12 text-center text-sm text-gray-400">该分类下暂无文件</div>
        ) : (
          <div className="max-h-[680px] overflow-y-auto p-2">
            {sortedVisible.map((filing, index) => (
              <a
                key={`${filing.accession_number}-${index}`}
                href={filing.doc_url || filing.index_url}
                target="_blank"
                rel="noreferrer"
                className="flex w-full items-start gap-4 rounded-lg border-b border-gray-50 px-4 py-3 text-left transition-colors last:border-0 hover:bg-gray-50"
              >
                <div className="mt-0.5 flex min-w-[72px] flex-shrink-0 flex-col items-center gap-1">
                  <span className="w-full rounded-md border border-blue-200 bg-blue-50 px-2.5 py-1 text-center text-xs font-bold text-blue-700">
                    {filing.form}
                  </span>
                  {filing.form_name && <span className="text-center text-[11px] leading-tight text-gray-500">{filing.form_name}</span>}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium text-gray-900">{filing.primary_doc_description || filing.form_desc || filing.form}</p>
                    {filing.items.map((item) => (
                      <span key={item.code} className="rounded bg-amber-50 px-2 py-0.5 text-xs text-amber-800">
                        {item.code}{item.label ? ` ${item.label}` : ''}
                      </span>
                    ))}
                  </div>
                  <p className="mt-1 text-xs text-gray-400">
                    提交 {filing.filing_date || '-'} · 报告期 {filing.report_date || '-'}
                  </p>
                </div>
                <ExternalLink className="mt-1 h-4 w-4 flex-shrink-0 text-gray-300" />
              </a>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function TranscriptsTab({
  ticker,
  transcripts,
  selectedUrl,
  detail,
  summary,
  listLoading,
  detailLoading,
  summaryLoading,
  error,
  summaryError,
  onLoadList,
  onSelectTranscript,
  onLoadSummary,
}: {
  ticker: string
  transcripts: TranscriptCandidate[]
  selectedUrl: string
  detail: TranscriptDetailResponse | null
  summary: TranscriptSummaryResponse | null
  listLoading: boolean
  detailLoading: boolean
  summaryLoading: boolean
  error: string
  summaryError: string
  onLoadList: () => void
  onSelectTranscript: (transcript: TranscriptCandidate) => void
  onLoadSummary: (detail: TranscriptDetailResponse) => void
}) {
  if (!ticker) return <EmptyState icon={MessageSquareText} text="输入股票代码后查看财报电话会" />
  if (error) return <ErrorState message={error} onRetry={onLoadList} />

  return (
    <div className="grid gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
      <section className="rounded-2xl border border-gray-100 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
          <div>
            <h2 className="text-sm font-bold text-gray-900">{ticker ? `${ticker} 会议` : '会议列表'}</h2>
            <p className="text-xs text-gray-500">{transcripts.length} 条记录</p>
          </div>
          <button
            onClick={onLoadList}
            disabled={listLoading || detailLoading}
            className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-semibold text-gray-600 hover:border-blue-300 hover:text-blue-700 disabled:opacity-50"
          >
            刷新
          </button>
        </div>
        <div className="max-h-[680px] overflow-y-auto p-3">
          {listLoading && transcripts.length === 0 && <div className="flex h-44 items-center justify-center text-sm text-gray-500">加载中...</div>}
          {!listLoading && transcripts.length === 0 && (
            <div className="flex h-44 flex-col items-center justify-center gap-2 text-center text-sm text-gray-500">
              <FileSearch className="h-8 w-8 text-gray-300" />
              <span>暂无会议记录</span>
            </div>
          )}
          <div className="space-y-2">
            {transcripts.map((item) => {
              const active = item.url === selectedUrl
              return (
                <button
                  key={item.url}
                  onClick={() => onSelectTranscript(item)}
                  className={`w-full rounded-lg border p-3 text-left transition ${
                    active ? 'border-blue-500 bg-blue-50 shadow-sm' : 'border-gray-200 bg-white hover:border-blue-200 hover:bg-gray-50'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div className={`mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg ${active ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-500'}`}>
                      <CalendarDays className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <p className="line-clamp-2 text-sm font-bold leading-5 text-gray-900">{item.title}</p>
                      <p className="mt-1 text-xs font-medium text-gray-500">{formatDate(item.published_at)}</p>
                    </div>
                  </div>
                </button>
              )
            })}
          </div>
        </div>
      </section>

      <section className="min-h-[520px] rounded-2xl border border-gray-100 bg-white p-5 shadow-sm">
        {!detail && !detailLoading && (
          <div className="flex h-full min-h-[420px] flex-col items-center justify-center gap-3 text-center text-gray-500">
            <MessageSquareText className="h-10 w-10 text-gray-300" />
            <p className="text-sm font-medium">选择一场会议查看 AI 总结和原文</p>
          </div>
        )}
        {detailLoading && <LoadingState text="加载逐字稿..." />}
        {detail && !detailLoading && (
          <div className="space-y-5">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div className="min-w-0">
                <div className="mb-2 flex flex-wrap items-center gap-2 text-xs font-bold text-gray-500">
                  <span className="rounded-md bg-gray-100 px-2 py-1">{detail.ticker}</span>
                  <span>{formatDate(detail.published_date)}</span>
                  <span>{detail.source}</span>
                </div>
                <h2 className="text-xl font-bold leading-tight text-gray-900">{detail.title}</h2>
              </div>
              <a
                href={detail.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-9 flex-shrink-0 items-center justify-center gap-2 rounded-lg border border-gray-200 px-3 text-sm font-semibold text-gray-700 transition hover:border-blue-300 hover:text-blue-700"
              >
                <ExternalLink className="h-4 w-4" />
                来源
              </a>
            </div>

            <div className="rounded-xl border border-blue-100 bg-blue-50 p-4">
              <h4 className="mb-2 flex items-center gap-2 text-sm font-bold text-blue-800">
                <Sparkles className="h-4 w-4" />
                AI 总结
              </h4>
              {summaryLoading && <p className="text-sm text-gray-500">AI 正在总结电话会议要点...</p>}
              {summaryError && (
                <button onClick={() => onLoadSummary(detail)} className="text-sm font-semibold text-red-600">
                  {summaryError}，点击重试
                </button>
              )}
              {!summaryLoading && !summaryError && summary && (
                <div className="space-y-4">
                  {summary.summary.overview && <p className="text-sm leading-7 text-gray-700">{summary.summary.overview}</p>}
                  <BulletList title="核心要点" items={summary.summary.key_points} />
                  <BulletList title="财务亮点" items={summary.summary.financial_highlights} />
                  {summary.summary.guidance && (
                    <div>
                      <h5 className="mb-1 text-sm font-bold text-gray-900">业绩指引与展望</h5>
                      <p className="text-sm leading-7 text-gray-700">{summary.summary.guidance}</p>
                    </div>
                  )}
                  <BulletList title="风险与挑战" items={summary.summary.risks} />
                </div>
              )}
            </div>

            <div className="grid gap-4 xl:grid-cols-2">
              <TranscriptText title="管理层发言" text={detail.prepared_remarks} />
              <TranscriptText title="问答环节 Q&A" text={detail.questions_and_answers} />
            </div>
          </div>
        )}
      </section>
    </div>
  )
}

function InvestmentScoreTab({
  ticker,
  analysis,
  loading,
  error,
  onAnalyze,
}: {
  ticker: string
  analysis: AnalysisResponse | null
  loading: boolean
  error: string
  onAnalyze: () => void
}) {
  if (!ticker) return <EmptyState icon={TrendingUp} text="输入股票代码后生成投资评分" />

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-blue-100 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-blue-600" />
              <h2 className="text-lg font-bold text-gray-900">{ticker} 投资评分</h2>
            </div>
            <p className="mt-1 text-sm text-gray-500">
              基于企业质量、财务健康、行业前景、市场预期、竞争格局和交易估值的六层框架。
            </p>
          </div>
          <button
            onClick={onAnalyze}
            disabled={loading}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 text-sm font-bold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <TrendingUp className="h-4 w-4" />}
            {loading ? '分析中...' : analysis ? '重新分析' : '生成评分'}
          </button>
        </div>
        {error && (
          <div className="mt-4 flex items-center gap-2 rounded-xl border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-700">
            <AlertCircle className="h-4 w-4" />
            {error}
          </div>
        )}
      </section>

      {analysis ? (
        <StockAnalysisCard analysis={analysis} />
      ) : !loading ? (
        <section className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {[
              ['企业质量', '管理层、护城河、品牌影响力'],
              ['财务健康', '收入、利润、自由现金流状况'],
              ['行业前景', '赛道增速、宏观趋势、竞争格局'],
              ['市场预期', '市场情绪、估值倍数、预期差'],
              ['竞争格局', '市场份额、进入壁垒、定价权'],
              ['交易估值', 'PE、PB、EV/EBITDA 历史水位'],
            ].map(([title, desc], index) => (
              <div key={title} className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                <div className="mb-1 flex items-center gap-2">
                  <span className="text-xs font-black text-blue-500">0{index + 1}</span>
                  <p className="text-sm font-bold text-gray-900">{title}</p>
                </div>
                <p className="text-xs leading-relaxed text-gray-500">{desc}</p>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  )
}

function BulletList({ title, items }: { title: string; items: string[] }) {
  if (!items || items.length === 0) return null
  return (
    <div>
      <h5 className="mb-1 text-sm font-bold text-gray-900">{title}</h5>
      <ul className="space-y-1.5">
        {items.map((item, index) => (
          <li key={`${title}-${index}`} className="flex gap-2 text-sm leading-6 text-gray-700">
            <span className="mt-2 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-blue-500" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function TranscriptText({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
      <h4 className="mb-3 text-sm font-bold text-gray-900">{title}</h4>
      <div className="max-h-[420px] space-y-3 overflow-y-auto pr-1 text-sm leading-7 text-gray-700">
        {(text || '暂无内容').split('\n\n').slice(0, 18).map((paragraph, index) => (
          <p key={`${title}-${index}`}>{paragraph}</p>
        ))}
      </div>
    </div>
  )
}

function LoadingState({ text }: { text: string }) {
  return (
    <div className="flex min-h-[320px] items-center justify-center gap-3 text-sm font-medium text-gray-500">
      <Loader2 className="h-5 w-5 animate-spin text-blue-500" />
      {text}
    </div>
  )
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex min-h-[260px] flex-col items-center justify-center gap-3 rounded-2xl border border-red-100 bg-red-50 text-center">
      <div className="flex items-center gap-2 text-sm font-medium text-red-700">
        <AlertCircle className="h-4 w-4" />
        <span>{message}</span>
      </div>
      <button
        onClick={onRetry}
        className="rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-semibold text-red-700 transition hover:bg-red-50"
      >
        重试
      </button>
    </div>
  )
}

function EmptyState({ icon: Icon, text }: { icon: typeof Building2; text: string }) {
  return (
    <div className="flex min-h-[320px] flex-col items-center justify-center gap-3 rounded-2xl border border-gray-100 bg-white text-center text-gray-500">
      <Icon className="h-10 w-10 text-gray-300" />
      <p className="text-sm font-medium">{text}</p>
    </div>
  )
}

export default function CompanyResearchPage() {
  const [query, setQuery] = useState(getInitialCompanyResearchSymbol)
  const [ticker, setTicker] = useState(getInitialCompanyResearchSymbol)
  const [activeTab, setActiveTab] = useState<ResearchTab>('overview')
  const embedded = isEmbeddedCompanyResearch()
  const didInitialLoad = useRef(false)
  const profileAbortRef = useRef<AbortController | null>(null)

  const [profile, setProfile] = useState<CompanyProfile | null>(null)
  const [profileLoading, setProfileLoading] = useState(false)
  const [profileError, setProfileError] = useState('')
  const [profileProgress, setProfileProgress] = useState<ProfileProgress | null>(null)

  const [filings, setFilings] = useState<CompanyFilingsResponse | null>(null)
  const [filingsLoading, setFilingsLoading] = useState(false)
  const [filingsError, setFilingsError] = useState('')

  const [transcripts, setTranscripts] = useState<TranscriptCandidate[]>([])
  const [selectedTranscriptUrl, setSelectedTranscriptUrl] = useState('')
  const [transcriptDetail, setTranscriptDetail] = useState<TranscriptDetailResponse | null>(null)
  const [transcriptSummary, setTranscriptSummary] = useState<TranscriptSummaryResponse | null>(null)
  const [transcriptListLoading, setTranscriptListLoading] = useState(false)
  const [transcriptDetailLoading, setTranscriptDetailLoading] = useState(false)
  const [transcriptError, setTranscriptError] = useState('')
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryError, setSummaryError] = useState('')

  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisError, setAnalysisError] = useState('')

  const loadProfile = useCallback(async (symbol: string) => {
    if (!symbol) return
    profileAbortRef.current?.abort()
    const controller = new AbortController()
    profileAbortRef.current = controller

    setProfileLoading(true)
    setProfileError('')
    setProfileProgress({ event: 'start', message: '正在解析股票代码' })
    setProfile(null)
    let completed = false
    const fallbackTimer = window.setTimeout(async () => {
      if (completed || controller.signal.aborted) return
      setProfileProgress({ event: 'generating', message: '生成时间较长，正在读取缓存结果' })
      try {
        const result = await fetchCompanyProfile(symbol)
        if (completed || profileAbortRef.current !== controller) return
        completed = true
        setProfile(result.profile)
        setProfileProgress(null)
        controller.abort()
      } catch {
        // 流式请求仍在继续，兜底失败时不打断主流程。
      } finally {
        if (completed && profileAbortRef.current === controller) {
          setProfileLoading(false)
        }
      }
    }, 35000)

    try {
      for await (const event of streamCompanyProfile(symbol, controller.signal)) {
        if (controller.signal.aborted) return
        if (event.event === 'error') {
          throw new Error(event.message)
        }
        if (event.event === 'done') {
          completed = true
          setProfile(event.data.profile)
          setProfileProgress(null)
          break
        }
        setProfileProgress({
          event: event.event,
          message: event.message,
          company: event.company,
        })
      }
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        setProfileError(getErrorMessage(error, '公司概览生成失败'))
      }
    } finally {
      window.clearTimeout(fallbackTimer)
      if (profileAbortRef.current === controller) {
        setProfileLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    return () => profileAbortRef.current?.abort()
  }, [])

  const loadFilings = useCallback(async (symbol: string) => {
    if (!symbol) return
    setFilingsLoading(true)
    setFilingsError('')
    setFilings(null)
    try {
      setFilings(await fetchCompanyFilings(symbol))
    } catch (error) {
      setFilingsError(getErrorMessage(error, 'SEC 文件加载失败'))
    } finally {
      setFilingsLoading(false)
    }
  }, [])

  const loadSummary = useCallback(async (detail: TranscriptDetailResponse) => {
    setSummaryLoading(true)
    setSummaryError('')
    setTranscriptSummary(null)
    try {
      setTranscriptSummary(await fetchTranscriptSummary(detail))
    } catch (error) {
      setSummaryError(getErrorMessage(error, '总结生成失败'))
    } finally {
      setSummaryLoading(false)
    }
  }, [])

  const loadTranscriptDetail = useCallback(async (symbol: string, transcript: TranscriptCandidate) => {
    setSelectedTranscriptUrl(transcript.url)
    setTranscriptDetail(null)
    setTranscriptSummary(null)
    setTranscriptDetailLoading(true)
    setTranscriptError('')
    setSummaryError('')
    try {
      const detail = await fetchTranscriptDetail(symbol, transcript.url)
      setTranscriptDetail(detail)
      loadSummary(detail)
    } catch (error) {
      setTranscriptError(getErrorMessage(error, '逐字稿加载失败'))
    } finally {
      setTranscriptDetailLoading(false)
    }
  }, [loadSummary])

  const loadTranscripts = useCallback(async (symbol: string) => {
    if (!symbol) return
    setTranscriptListLoading(true)
    setTranscriptError('')
    setTranscripts([])
    setSelectedTranscriptUrl('')
    setTranscriptDetail(null)
    setTranscriptSummary(null)
    try {
      const result = await fetchTranscriptList(symbol)
      setTranscripts(result.transcripts)
      if (result.transcripts.length > 0) {
        await loadTranscriptDetail(symbol, result.transcripts[0])
      }
    } catch (error) {
      setTranscriptError(getErrorMessage(error, '财报电话会议列表加载失败'))
    } finally {
      setTranscriptListLoading(false)
    }
  }, [loadTranscriptDetail])

  const loadAnalysis = useCallback(async (symbol: string) => {
    if (!symbol) return
    setAnalysisLoading(true)
    setAnalysisError('')
    try {
      setAnalysis(await analyzeStock(symbol))
    } catch (error) {
      setAnalysisError(getErrorMessage(error, '投资评分分析失败'))
    } finally {
      setAnalysisLoading(false)
    }
  }, [])

  const runSearch = useCallback((raw: string) => {
    const symbol = normalizeTicker(raw)
    if (!symbol) return
    setQuery(symbol)
    setTicker(symbol)
    setAnalysis(null)
    setAnalysisError('')
    loadProfile(symbol)
    loadFilings(symbol)
    loadTranscripts(symbol)
  }, [loadFilings, loadProfile, loadTranscripts])

  useEffect(() => {
    if (didInitialLoad.current) return
    didInitialLoad.current = true
    runSearch(ticker)
  }, [runSearch, ticker])

  const content = (
    <div className={embedded ? 'space-y-4 p-4' : 'space-y-5'}>
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-600 text-white shadow-sm">
              <Building2 className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">企业研究</h1>
              <p className="text-sm text-gray-500">公司概览、SEC 文件、财报电话会统一入口</p>
            </div>
          </div>
        </div>

        <section className="rounded-2xl border border-gray-100 bg-white p-4 shadow-sm">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value.toUpperCase())}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') runSearch(query)
                }}
                placeholder="股票代码或 CIK，如 NVDA / AAPL / 320193"
                className="h-11 w-full rounded-xl border border-gray-200 bg-gray-50 pl-10 pr-3 text-base font-semibold tracking-wide text-gray-900 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
              />
            </div>
            <button
              onClick={() => runSearch(query)}
              disabled={profileLoading || filingsLoading || transcriptListLoading}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 text-sm font-bold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
            >
              {profileLoading || filingsLoading || transcriptListLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Search className="h-4 w-4" />
              )}
              查询
            </button>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {QUICK_TICKERS.map((symbol) => (
              <button
                key={symbol}
                onClick={() => runSearch(symbol)}
                className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-bold text-gray-700 transition hover:border-blue-500 hover:text-blue-700"
              >
                {symbol}
              </button>
            ))}
          </div>
        </section>

        <div className="inline-flex max-w-full items-center gap-1 overflow-x-auto rounded-xl border border-gray-200 bg-white p-1">
          {TABS.map((tab) => {
            const Icon = tab.icon
            const active = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`inline-flex h-9 items-center gap-2 rounded-lg px-3 text-sm font-semibold transition ${
                  active ? 'bg-blue-600 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </button>
            )
          })}
        </div>

        {activeTab === 'overview' && (
          <CompanyOverviewTab
            ticker={ticker}
            profile={profile}
            loading={profileLoading}
            progress={profileProgress}
            error={profileError}
            onRetry={() => loadProfile(ticker)}
          />
        )}

        {activeTab === 'sec' && (
          <SecFilingsTab
            data={filings}
            loading={filingsLoading}
            error={filingsError}
            onRetry={() => loadFilings(ticker)}
          />
        )}

        {activeTab === 'transcripts' && (
          <TranscriptsTab
            ticker={ticker}
            transcripts={transcripts}
            selectedUrl={selectedTranscriptUrl}
            detail={transcriptDetail}
            summary={transcriptSummary}
            listLoading={transcriptListLoading}
            detailLoading={transcriptDetailLoading}
            summaryLoading={summaryLoading}
            error={transcriptError}
            summaryError={summaryError}
            onLoadList={() => loadTranscripts(ticker)}
            onSelectTranscript={(transcript) => loadTranscriptDetail(ticker, transcript)}
            onLoadSummary={loadSummary}
          />
        )}

        {activeTab === 'score' && (
          <InvestmentScoreTab
            ticker={ticker}
            analysis={analysis}
            loading={analysisLoading}
            error={analysisError}
            onAnalyze={() => loadAnalysis(ticker)}
          />
        )}
      </div>
  )

  if (embedded) return content

  return (
    <DashboardShell>
      {content}
    </DashboardShell>
  )
}
