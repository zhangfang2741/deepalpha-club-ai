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

// 估值状态配置
const LABEL_CONFIG: Record<LabelEn, { dot: string; badge: string; bar: string; text: string }> = {
  extreme_undervalue: { dot: 'bg-blue-700',   badge: 'bg-blue-700 text-white',          bar: 'bg-blue-700',   text: 'text-blue-700' },
  undervalue:         { dot: 'bg-blue-400',   badge: 'bg-blue-100 text-blue-700',       bar: 'bg-blue-400',   text: 'text-blue-600' },
  neutral:            { dot: 'bg-slate-300',  badge: 'bg-slate-100 text-slate-500',     bar: 'bg-slate-300',  text: 'text-slate-500' },
  overvalue:          { dot: 'bg-orange-400', badge: 'bg-orange-100 text-orange-600',   bar: 'bg-orange-400', text: 'text-orange-500' },
  extreme_overvalue:  { dot: 'bg-red-500',    badge: 'bg-red-100 text-red-600',         bar: 'bg-red-500',    text: 'text-red-500' },
  insufficient:       { dot: 'bg-slate-200',  badge: 'bg-slate-50 text-slate-300',      bar: 'bg-slate-200',  text: 'text-slate-300' },
}

// 计算板块主要估值状态（取有数据的ETF中出现频率最高的）
function getSectorDominantLabel(etfs: ETFValuationSummaryItem[]): LabelEn {
  const withData = etfs.filter(e => e.label_en && e.label_en !== 'insufficient')
  if (withData.length === 0) return 'insufficient'
  const counts: Partial<Record<LabelEn, number>> = {}
  for (const e of withData) {
    const k = e.label_en as LabelEn
    counts[k] = (counts[k] ?? 0) + 1
  }
  // 权重：高/低估优先显示
  const priority: LabelEn[] = ['extreme_undervalue', 'extreme_overvalue', 'undervalue', 'overvalue', 'neutral']
  for (const k of priority) {
    if ((counts[k] ?? 0) >= Math.ceil(withData.length / 2)) return k
  }
  return 'neutral'
}

// z-score 小徽章
function ZBadge({ item }: { item: ETFValuationSummaryItem }) {
  const key = (item.label_en || 'insufficient') as LabelEn
  const cfg = LABEL_CONFIG[key]
  const zStr = item.z_score !== null
    ? (item.z_score >= 0 ? '+' : '') + item.z_score.toFixed(2)
    : '—'
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold shrink-0 ${cfg.badge}`}>
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
  const cfg = LABEL_CONFIG[key]
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-left transition-all ${
        active ? 'bg-blue-50 ring-1 ring-blue-300' : 'hover:bg-slate-50'
      }`}
    >
      {/* 估值颜色条 */}
      <span className={`flex-shrink-0 w-0.5 h-4 rounded-full ${cfg.bar}`} />
      {/* 代码 */}
      <span className="font-mono text-[11px] font-bold text-slate-700 w-9 shrink-0">
        {item.symbol}
      </span>
      {/* 名称 */}
      <span className="text-[10px] text-slate-400 flex-1 min-w-0 truncate">{item.name.slice(0, 10)}</span>
      {/* z 徽章 */}
      <ZBadge item={item} />
    </button>
  )
}

function SectorHeader({
  label,
  etfs,
  expanded,
  onToggle,
}: {
  label: string
  etfs: ETFValuationSummaryItem[]
  expanded: boolean
  onToggle: () => void
}) {
  const dominant = getSectorDominantLabel(etfs)
  const cfg = LABEL_CONFIG[dominant]
  const withData = etfs.filter(e => e.z_score !== null)
  const underCnt = withData.filter(e => (e.z_score ?? 0) < -1).length
  const overCnt  = withData.filter(e => (e.z_score ?? 0) >= 1).length

  return (
    <button
      type="button"
      onClick={onToggle}
      className="w-full flex items-center gap-2 px-2 py-2.5 rounded-xl hover:bg-slate-100/80 transition-colors group"
    >
      {/* 展开箭头 */}
      <span
        className="text-slate-400 text-[9px] group-hover:text-slate-600 transition-transform duration-200 shrink-0"
        style={{ display: 'inline-block', transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)' }}
      >
        ▶
      </span>
      {/* 板块名 */}
      <span className="flex-1 text-xs font-semibold text-slate-700 text-left truncate">{label}</span>
      {/* 低估/高估小标 */}
      {withData.length > 0 && (
        <span className="flex items-center gap-1 shrink-0">
          {underCnt > 0 && (
            <span className="text-[9px] font-bold text-blue-600 bg-blue-50 px-1 py-0.5 rounded">
              ↓{underCnt}
            </span>
          )}
          {overCnt > 0 && (
            <span className="text-[9px] font-bold text-orange-500 bg-orange-50 px-1 py-0.5 rounded">
              ↑{overCnt}
            </span>
          )}
        </span>
      )}
      {/* 主色点 */}
      <span className={`w-2 h-2 rounded-full shrink-0 ${cfg.dot}`} />
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

  useEffect(() => {
    fetchETFSummary()
      .then((res) => {
        setSummary(res)
        setSummaryLoading(false)
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

  // 顶部摘要统计：基于 ETF 汇总数据
  const etfList = summary?.etfs ?? []
  const etfWithData = etfList.filter(e => e.z_score !== null)
  const etfUnder  = etfWithData.filter(e => (e.z_score ?? 0) <= -1).length
  const etfOver   = etfWithData.filter(e => (e.z_score ?? 0) >= 1).length
  const etfNeutral = etfWithData.length - etfUnder - etfOver

  return (
    <div className="space-y-3">
      {/* 顶部摘要条 */}
      <div className="flex items-center gap-3 px-4 py-2.5 rounded-xl border border-slate-200 bg-white flex-wrap text-xs text-slate-500 shadow-sm">
        <span className="text-slate-400">
          行业 PE 截至 <span className="font-semibold text-slate-600">{data.as_of || '—'}</span>
        </span>
        <span className="text-slate-200">|</span>
        <span className="text-slate-400">ETF 近 5 年季度 PE · z-score</span>
        {etfList.length > 0 && (
          <>
            <span className="text-slate-200">|</span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-blue-500 inline-block" />
              <span className="text-blue-600 font-medium">低估 {etfUnder}</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-slate-300 inline-block" />
              <span>中性 {etfNeutral}</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-orange-400 inline-block" />
              <span className="text-orange-500 font-medium">高估 {etfOver}</span>
            </span>
          </>
        )}
      </div>

      {/* 主区域 */}
      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-3">

        {/* ── 左侧：行业 Accordion + ETF 列表 ── */}
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden self-start">
          {/* 左侧标题 */}
          <div className="px-3 py-2.5 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white">
            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
              行业 / ETF
            </div>
            <div className="text-[9px] text-slate-300 mt-0.5">↓低估 · ↑高估 · 点击查看详情</div>
          </div>

          <div className="px-1.5 py-1.5 max-h-[700px] overflow-y-auto">
            {summaryLoading ? (
              <div className="flex flex-col items-center justify-center py-16 gap-3">
                <Spinner className="w-5 h-5 text-slate-400" />
                <div className="text-xs text-slate-400">正在加载 ETF 估值数据…</div>
                <div className="text-[10px] text-slate-300">首次约 10 秒，之后 4h 缓存</div>
              </div>
            ) : summaryError ? (
              <div className="py-8 text-center text-sm text-red-400">{summaryError}</div>
            ) : (
              <div className="space-y-0.5">
                {sectorGroups.map((sg) => {
                  const expanded = expandedSectors.has(sg.key)
                  return (
                    <div key={sg.key}>
                      <SectorHeader
                        label={sg.label}
                        etfs={sg.etfs}
                        expanded={expanded}
                        onToggle={() => toggleSector(sg.key)}
                      />
                      {expanded && (
                        <div className="ml-2 mb-1 space-y-0.5 border-l-2 border-slate-100 pl-2">
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
                })}
              </div>
            )}
          </div>
        </div>

        {/* ── 右侧：详情面板 ── */}
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5 min-h-[520px] flex flex-col">
          {!selectedSymbol ? (
            <div className="flex flex-col items-center justify-center flex-1 text-slate-400 gap-3">
              <div className="w-12 h-12 rounded-2xl bg-slate-100 flex items-center justify-center">
                <svg className="w-6 h-6 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              </div>
              <div className="text-sm font-medium text-slate-400">点击左侧 ETF 查看估值详情</div>
            </div>
          ) : detailLoading ? (
            <div className="flex items-center justify-center flex-1 gap-3">
              <Spinner className="w-5 h-5 text-slate-400" />
              <span className="text-sm text-slate-400">加载中…</span>
            </div>
          ) : detailError ? (
            <div className="flex items-center justify-center flex-1 text-red-400 text-sm">
              {detailError}
            </div>
          ) : detail ? (
            <SectorDetailPanel detail={detail} />
          ) : null}
        </div>
      </div>

      {/* 底部说明 */}
      <p className="text-[11px] text-slate-400 px-1 leading-relaxed">
        <span className="font-medium text-slate-500">z-score</span> = (当前季度 PE − 近 5 年历史均值) ÷ 标准差。
        子板块 ETF 使用其所属 GICS 行业 PE 作为近似基准。
        商品、债券、加密类 ETF 无 PE 数据属正常现象。
      </p>
    </div>
  )
}
