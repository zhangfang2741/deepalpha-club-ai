'use client'

import { useEffect, useState } from 'react'
import type { SectorValuation, ETFPricePoint } from '@/lib/api/valuation'
import { fetchETFPrice } from '@/lib/api/valuation'
import Spinner from '@/components/ui/Spinner'
import SectorPEChart from './SectorPEChart'
import SectorETFPriceChart from './SectorETFPriceChart'

interface Props {
  sv: SectorValuation
}

export default function SectorDetailPanel({ sv }: Props) {
  const [prices, setPrices] = useState<ETFPricePoint[]>([])
  const [priceLoading, setPriceLoading] = useState(false)
  const [priceError, setPriceError] = useState('')

  useEffect(() => {
    if (!sv.etf_symbol) {
      setPrices([])
      setPriceError('该行业暂无代理 ETF')
      return
    }

    let cancelled = false
    setPriceLoading(true)
    setPriceError('')
    fetchETFPrice(sv.etf_symbol, 730)
      .then((res) => {
        if (cancelled) return
        if (res.prices.length === 0) {
          setPriceError(`暂无 ${sv.etf_symbol} 历史价格数据`)
          setPrices([])
        } else {
          setPrices(res.prices)
        }
      })
      .catch(() => {
        if (!cancelled) setPriceError('价格数据加载失败')
      })
      .finally(() => {
        if (!cancelled) setPriceLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [sv.etf_symbol])

  const hasPEData =
    sv.hist_pe.length >= 2 && sv.hist_mean !== null && sv.hist_std !== null

  const zStr =
    sv.z_score !== null ? (sv.z_score >= 0 ? '+' : '') + sv.z_score.toFixed(2) : '—'
  const zColor =
    sv.z_score === null
      ? '#94a3b8'
      : sv.z_score <= -2
        ? '#1d4ed8'
        : sv.z_score <= -1
          ? '#3b82f6'
          : sv.z_score < 1
            ? '#64748b'
            : sv.z_score < 2
              ? '#f97316'
              : '#dc2626'

  return (
    <div className="space-y-5">
      {/* 头部 */}
      <div className="flex items-start justify-between gap-3 pb-4 border-b border-slate-100">
        <div>
          <div className="flex items-baseline gap-3">
            <h3 className="text-xl font-bold text-slate-900">{sv.sector_cn}</h3>
            <span className="text-sm text-slate-400">{sv.sector}</span>
            {sv.etf_symbol && (
              <span className="px-2 py-0.5 rounded-md bg-slate-100 text-xs font-mono font-bold text-slate-700">
                {sv.etf_symbol}
              </span>
            )}
          </div>
          <div className="text-xs text-slate-500 mt-1">
            <span>{sv.label}</span>
            <span className="text-slate-300 mx-2">·</span>
            <span>样本 {sv.data_quarters} 个季度</span>
          </div>
        </div>
        <div className="text-right">
          <div className="text-3xl font-mono font-extrabold tracking-tight" style={{ color: zColor }}>
            {zStr}σ
          </div>
          <div className="text-xs text-slate-400 mt-0.5">z-score</div>
        </div>
      </div>

      {/* ETF 价格图表 */}
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-bold text-slate-800">代理 ETF 价格</h4>
          <span className="text-xs text-slate-400">近 2 年日线</span>
        </div>
        {priceLoading ? (
          <div className="flex items-center justify-center h-[220px]">
            <Spinner className="w-5 h-5 text-slate-400" />
          </div>
        ) : priceError ? (
          <div className="flex items-center justify-center h-[220px] text-sm text-slate-400">
            {priceError}
          </div>
        ) : (
          <SectorETFPriceChart symbol={sv.etf_symbol} prices={prices} />
        )}
      </div>

      {/* PE z-score 图表 */}
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-bold text-slate-800">PE 历史与 σ 区块</h4>
          <span className="text-xs text-slate-400">近 10 年季度 PE</span>
        </div>
        {hasPEData ? (
          <SectorPEChart
            histPE={sv.hist_pe as { date: string; pe: number }[]}
            mean={sv.hist_mean as number}
            std={sv.hist_std as number}
            currentPE={sv.current_pe}
            currentDate={sv.hist_pe[sv.hist_pe.length - 1]?.date ?? ''}
          />
        ) : (
          <div className="flex items-center justify-center h-[200px] text-sm text-slate-400">
            历史 PE 数据不足
          </div>
        )}
        {hasPEData && (
          <div className="flex items-center gap-3 mt-3 text-xs text-slate-400 flex-wrap">
            <span className="flex items-center gap-1">
              <span className="inline-block w-3 h-3 rounded-sm" style={{ background: 'rgba(29,78,216,0.18)' }} />
              ≤ -2σ
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block w-3 h-3 rounded-sm" style={{ background: 'rgba(96,165,250,0.22)' }} />
              -2 ~ -1σ
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block w-3 h-3 rounded-sm border border-slate-200" style={{ background: 'rgba(241,245,249,0.65)' }} />
              -1 ~ +1σ
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block w-3 h-3 rounded-sm" style={{ background: 'rgba(251,146,60,0.22)' }} />
              +1 ~ +2σ
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block w-3 h-3 rounded-sm" style={{ background: 'rgba(220,38,38,0.20)' }} />
              ≥ +2σ
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
