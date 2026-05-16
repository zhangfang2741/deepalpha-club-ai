'use client'

import { useEffect, useMemo, useState } from 'react'
import type { SectorValuation, SectorValuationResponse } from '@/lib/api/valuation'
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

const LABEL_BG: Record<LabelEn, string> = {
  extreme_undervalue: 'bg-blue-700',
  undervalue: 'bg-blue-400',
  neutral: 'bg-slate-200',
  overvalue: 'bg-orange-400',
  extreme_overvalue: 'bg-red-600',
  insufficient: 'bg-slate-100',
}

const LABEL_TEXT: Record<LabelEn, string> = {
  extreme_undervalue: 'text-white',
  undervalue: 'text-white',
  neutral: 'text-slate-700',
  overvalue: 'text-white',
  extreme_overvalue: 'text-white',
  insufficient: 'text-slate-400',
}

const LABEL_ORDER: Record<LabelEn, number> = {
  extreme_undervalue: 0,
  undervalue: 1,
  neutral: 2,
  overvalue: 3,
  extreme_overvalue: 4,
  insufficient: 5,
}

function SectorListItem({
  sv,
  active,
  onClick,
}: {
  sv: SectorValuation
  active: boolean
  onClick: () => void
}) {
  const key = (sv.label_en || 'insufficient') as LabelEn
  const zStr =
    sv.z_score !== null ? (sv.z_score >= 0 ? '+' : '') + sv.z_score.toFixed(2) : '—'

  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full text-left px-3 py-2.5 rounded-lg transition-all border ${
        active
          ? 'border-blue-500 bg-blue-50 ring-2 ring-blue-100'
          : 'border-transparent hover:bg-slate-50 hover:border-slate-200'
      }`}
    >
      <div className="flex items-center gap-2.5">
        <span className={`inline-block w-1 h-8 rounded-full ${LABEL_BG[key]}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="font-semibold text-sm text-slate-900 truncate">
              {sv.sector_cn}
            </span>
            {sv.etf_symbol && (
              <span className="text-[10px] font-mono text-slate-400 font-bold">
                {sv.etf_symbol}
              </span>
            )}
          </div>
          <div className="text-[11px] text-slate-400">{sv.label}</div>
        </div>
        <span
          className={`px-2 py-0.5 rounded-md text-xs font-mono font-bold ${LABEL_BG[key]} ${LABEL_TEXT[key]} whitespace-nowrap`}
        >
          {zStr}σ
        </span>
      </div>
    </button>
  )
}

export default function SectorValuationGrid({ data }: Props) {
  const sorted = useMemo(() => {
    return [...data.sectors].sort((a, b) => {
      const ak = (a.label_en || 'insufficient') as LabelEn
      const bk = (b.label_en || 'insufficient') as LabelEn
      const orderDiff = (LABEL_ORDER[ak] ?? 5) - (LABEL_ORDER[bk] ?? 5)
      if (orderDiff !== 0) return orderDiff
      const az = a.z_score ?? 0
      const bz = b.z_score ?? 0
      return az - bz
    })
  }, [data.sectors])

  const [selectedSector, setSelectedSector] = useState<string | null>(null)
  useEffect(() => {
    if (selectedSector === null) {
      const first = sorted.find((s) => s.z_score !== null)
      if (first) setSelectedSector(first.sector)
    }
  }, [sorted, selectedSector])

  const selected = useMemo(
    () => sorted.find((s) => s.sector === selectedSector) ?? null,
    [sorted, selectedSector],
  )

  const withData = sorted.filter((s) => s.z_score !== null)
  const undervalued = withData.filter((s) => (s.z_score ?? 0) < -1)
  const overvalued = withData.filter((s) => (s.z_score ?? 0) >= 1)

  return (
    <div className="space-y-4">
      {/* 顶部摘要 */}
      <div className="flex items-center gap-4 px-4 py-3 rounded-xl border border-gray-200 bg-gray-50 flex-wrap text-xs text-gray-500">
        <span>
          数据截至{' '}
          <span className="font-semibold text-gray-700">{data.as_of || '—'}</span>
        </span>
        <span className="text-gray-300">·</span>
        <span>
          历史基准 <span className="font-semibold text-gray-700">10 年</span>（季度 PE）
        </span>
        <span className="text-gray-300">·</span>
        <span>S&P 500 GICS 行业</span>
        <div className="ml-auto flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-3 rounded-sm bg-blue-600" />
            低估 ({undervalued.length})
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-3 rounded-sm bg-orange-400" />
            高估 ({overvalued.length})
          </span>
        </div>
      </div>

      {/* 主区域：左列表 + 右详情 */}
      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
        {/* 左侧行业列表 */}
        <div className="rounded-xl border border-slate-200 bg-white p-2 self-start">
          <div className="px-2 pt-1 pb-2 text-[11px] uppercase tracking-wider text-slate-400 font-bold">
            行业（按 z-score 升序）
          </div>
          <div className="space-y-1 max-h-[640px] overflow-y-auto">
            {sorted.map((sv) => (
              <SectorListItem
                key={sv.sector}
                sv={sv}
                active={sv.sector === selectedSector}
                onClick={() => setSelectedSector(sv.sector)}
              />
            ))}
          </div>
        </div>

        {/* 右侧详情面板 */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 min-h-[400px]">
          {selected ? (
            <SectorDetailPanel sv={selected} />
          ) : (
            <div className="flex items-center justify-center h-full text-sm text-slate-400">
              请选择左侧行业查看详情
            </div>
          )}
        </div>
      </div>

      {/* 底部说明 */}
      <p className="text-xs text-gray-400 px-1 leading-relaxed">
        <span className="font-medium text-gray-500">z-score</span> = (当前 PE − 10 年历史均值) ÷
        标准差。点击左侧行业查看其代理 SPDR ETF（如信息技术对应
        XLK）的近 2 年价格曲线，以及该行业 10 年季度 PE 在 ±1σ / ±2σ
        区间内的历史分布。
      </p>
    </div>
  )
}
