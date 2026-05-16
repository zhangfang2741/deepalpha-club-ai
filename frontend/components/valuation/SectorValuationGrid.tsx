'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import type {
  ETFValuationDetail,
  ETFValuationSummaryItem,
  ETFValuationSummaryResponse,
  SectorValuationResponse,
} from '@/lib/api/valuation'
import { fetchETFDetail, fetchETFSummary } from '@/lib/api/valuation'
import Spinner from '@/components/ui/Spinner'
import SectorDetailPanel from './SectorDetailPanel'

interface Props {
  data: SectorValuationResponse
}

type LabelEn =
  | 'extreme_undervalue'
  | 'undervalue'
  | 'neutral'
  | 'overvalue'
  | 'extreme_overvalue'
  | 'insufficient'

const Z_DOT_COLOR: Record<LabelEn, string> = {
  extreme_undervalue: 'bg-blue-700',
  undervalue: 'bg-blue-400',
  neutral: 'bg-slate-300',
  overvalue: 'bg-orange-400',
  extreme_overvalue: 'bg-red-500',
  insufficient: 'bg-slate-200',
}

const Z_TEXT_COLOR: Record<LabelEn, string> = {
  extreme_undervalue: 'text-blue-700',
  undervalue: 'text-blue-500',
  neutral: 'text-slate-400',
  overvalue: 'text-orange-500',
  extreme_overvalue: 'text-red-500',
  insufficient: 'text-slate-300',
}

const Z_BADGE: Record<LabelEn, string> = {
  extreme_undervalue: 'bg-blue-700 text-white',
  undervalue: 'bg-blue-100 text-blue-700',
  neutral: 'bg-slate-100 text-slate-500',
  overvalue: 'bg-orange-100 text-orange-600',
  extreme_overvalue: 'bg-red-100 text-red-600',
  insufficient: 'bg-slate-50 text-slate-300',
}

function zBadge(item: ETFValuationSummaryItem) {
  const key = (item.label_en || 'insufficient') as LabelEn
  const zStr =
    item.z_score !== null ? (item.z_score >= 0 ? '+' : '') + item.z_score.toFixed(2) : '—'
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold ${Z_BADGE[key]}`}>
      {zStr}σ
    </span>
  )
}

function ETFRow({
  item,
  active,
  onClick,
}: {
  item: ETFValuationSummaryItem
  active: boolean
  onClick: () => void
}) {
  const key = (item.label_en || 'insufficient') as LabelEn
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left transition-all ${
        active
          ? 'bg-blue-50 ring-1 ring-blue-400'
          : 'hover:bg-slate-50'
      }`}
    >
      <span className={`flex-shrink-0 w-1.5 h-1.5 rounded-full ${Z_DOT_COLOR[key]}`} />
      <span className="font-mono text-xs font-bold text-slate-700 w-10 flex-shrink-0">
        {item.symbol}
      </span>
      <span className="text-[11px] text-slate-400 flex-1 min-w-0 truncate">{item.name.slice(0, 12)}</span>
      {zBadge(item)}
    </button>
  )
}

function SectorHeader({
  sectorKey,
  label,
  count,
  withDataCount,
  expanded,
  onToggle,
}: {
  sectorKey: string
  label: string
  count: number
  withDataCount: number
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="w-full flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-slate-100 transition-colors group"
    >
      <span
        className={`text-slate-400 group-hover:text-slate-600 transition-transform duration-200 ${expanded ? 'rotate-90' : ''}`}
        style={{ display: 'inline-block' }}
      >
        ▶
      </span>
      <span className="flex-1 text-xs font-bold text-slate-700 text-left">{label}</span>
      <span className="text-[10px] text-slate-400 tabular-nums">{withDataCount}/{count}</span>
    </button>
  )
}

export default function SectorValuationGrid({ data }: Props) {
  const [summary, setSummary] = useState<ETFValuationSummaryResponse | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(true)
  const [summaryError, setSummaryError] = useState('')

  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)
  const [detail, setDetail] = useState<ETFValuationDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')

  const [expandedSectors, setExpandedSectors] = useState<Set<string>>(new Set())

  const detailAbort = useRef<AbortController | null>(null)

  // Load ETF summary on mount
  useEffect(() => {
    fetchETFSummary()
      .then((res) => {
        setSummary(res)
        setSummaryLoading(false)
        // Auto-expand first sector, auto-select first ETF with PE data
        if (res.etfs.length > 0) {
          const firstSector = res.etfs[0].sector_key
          setExpandedSectors(new Set([firstSector]))
          const firstWithData = res.etfs.find((e) => e.z_score !== null)
          if (firstWithData) setSelectedSymbol(firstWithData.symbol)
        }
      })
      .catch(() => {
        setSummaryError('ETF 估值数据加载失败')
        setSummaryLoading(false)
      })
  }, [])

  // Load detail when symbol changes
  useEffect(() => {
    if (!selectedSymbol) return
    detailAbort.current?.abort()
    detailAbort.current = new AbortController()

    setDetailLoading(true)
    setDetailError('')
    fetchETFDetail(selectedSymbol)
      .then((res) => {
        setDetail(res)
        setDetailLoading(false)
      })
      .catch(() => {
        setDetailError('数据加载失败，请重试')
        setDetailLoading(false)
      })
  }, [selectedSymbol])

  // Group ETFs by sector_key preserving backend order
  const sectorGroups = useMemo(() => {
    if (!summary) return []
    const order: string[] = []
    const map = new Map<string, ETFValuationSummaryItem[]>()
    for (const etf of summary.etfs) {
      if (!map.has(etf.sector_key)) {
        order.push(etf.sector_key)
        map.set(etf.sector_key, [])
      }
      map.get(etf.sector_key)!.push(etf)
    }
    return order.map((key) => ({
      key,
      label: key.slice(3),
      etfs: map.get(key) ?? [],
    }))
  }, [summary])

  const toggleSector = (key: string) => {
    setExpandedSectors((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  // Summary stats from sector data
  const withData = data.sectors.filter((s) => s.z_score !== null)
  const undervalued = withData.filter((s) => (s.z_score ?? 0) < -1)
  const overvalued = withData.filter((s) => (s.z_score ?? 0) >= 1)

  return (
    <div className="space-y-4">
      {/* 顶部摘要条 */}
      <div className="flex items-center gap-4 px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 flex-wrap text-xs text-slate-500">
        <span>
          行业 PE 截至{' '}
          <span className="font-semibold text-slate-700">{data.as_of || '—'}</span>
        </span>
        <span className="text-slate-300">·</span>
        <span>
          10 年历史基准{' '}
          <span className="font-semibold text-slate-700">（季度 GICS PE）</span>
        </span>
        <span className="text-slate-300">·</span>
        <span>ETF 数据：近 5 年季度 PE</span>
        <div className="ml-auto flex items-center gap-3">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-blue-600 inline-block" />
            行业低估 ({undervalued.length})
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-orange-400 inline-block" />
            行业高估 ({overvalued.length})
          </span>
        </div>
      </div>

      {/* 主区域 */}
      <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-4">

        {/* ── 左侧：行业 Accordion + ETF 列表 ── */}
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden self-start">
          <div className="px-4 py-3 border-b border-slate-100 bg-slate-50/60">
            <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">
              行业 / ETF（点击查看估值图）
            </div>
          </div>
          <div className="p-2 max-h-[680px] overflow-y-auto">
            {summaryLoading ? (
              <div className="flex flex-col items-center justify-center py-16 gap-3">
                <Spinner className="w-6 h-6 text-slate-400" />
                <div className="text-xs text-slate-400">正在加载 ETF 估值数据…</div>
                <div className="text-[10px] text-slate-300">首次加载约 10 秒，之后 4h 缓存</div>
              </div>
            ) : summaryError ? (
              <div className="py-8 text-center text-sm text-red-400">{summaryError}</div>
            ) : (
              sectorGroups.map((sg) => {
                const expanded = expandedSectors.has(sg.key)
                const withDataCount = sg.etfs.filter((e) => e.z_score !== null).length
                return (
                  <div key={sg.key} className="mb-0.5">
                    <SectorHeader
                      sectorKey={sg.key}
                      label={sg.label}
                      count={sg.etfs.length}
                      withDataCount={withDataCount}
                      expanded={expanded}
                      onToggle={() => toggleSector(sg.key)}
                    />
                    {expanded && (
                      <div className="ml-3 mt-0.5 mb-1 space-y-0.5 border-l-2 border-slate-100 pl-2">
                        {sg.etfs.map((etf) => (
                          <ETFRow
                            key={etf.symbol}
                            item={etf}
                            active={etf.symbol === selectedSymbol}
                            onClick={() => setSelectedSymbol(etf.symbol)}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                )
              })
            )}
          </div>
        </div>

        {/* ── 右侧：详情面板 ── */}
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-6 min-h-[480px]">
          {!selectedSymbol ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-400 gap-3">
              <div className="text-4xl">←</div>
              <div className="text-sm font-medium">点击左侧 ETF 查看估值详情</div>
            </div>
          ) : detailLoading ? (
            <div className="flex items-center justify-center h-full gap-3">
              <Spinner className="w-6 h-6 text-slate-400" />
              <span className="text-sm text-slate-400">加载中…</span>
            </div>
          ) : detailError ? (
            <div className="flex items-center justify-center h-full text-red-400 text-sm">
              {detailError}
            </div>
          ) : detail ? (
            <SectorDetailPanel detail={detail} />
          ) : null}
        </div>
      </div>

      {/* 底部说明 */}
      <p className="text-xs text-slate-400 px-1 leading-relaxed">
        <span className="font-medium text-slate-500">z-score</span> = (当前季度 PE − 近 5 年历史均值) ÷
        标准差。图表展示各 ETF 在 ±1σ / ±2σ 区间内的历史 PE 分布。商品、债券、加密类 ETF 无 PE 数据。
      </p>
    </div>
  )
}
