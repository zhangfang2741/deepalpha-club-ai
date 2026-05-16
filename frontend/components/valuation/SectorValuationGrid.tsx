'use client'

import type { SectorValuation, SectorValuationResponse } from '@/lib/api/valuation'

interface Props {
  data: SectorValuationResponse
}

type LabelEn = 'extreme_undervalue' | 'undervalue' | 'neutral' | 'overvalue' | 'extreme_overvalue' | 'insufficient'

const LABEL_STYLE: Record<LabelEn, { bg: string; text: string; badge: string }> = {
  extreme_undervalue: {
    bg: 'bg-blue-700',
    text: 'text-white',
    badge: 'bg-blue-900/40 text-blue-100',
  },
  undervalue: {
    bg: 'bg-blue-400',
    text: 'text-white',
    badge: 'bg-blue-600/30 text-blue-50',
  },
  neutral: {
    bg: 'bg-slate-100',
    text: 'text-slate-700',
    badge: 'bg-slate-200 text-slate-500',
  },
  overvalue: {
    bg: 'bg-orange-400',
    text: 'text-white',
    badge: 'bg-orange-600/30 text-orange-50',
  },
  extreme_overvalue: {
    bg: 'bg-red-600',
    text: 'text-white',
    badge: 'bg-red-800/40 text-red-100',
  },
  insufficient: {
    bg: 'bg-slate-50',
    text: 'text-slate-400',
    badge: 'bg-slate-100 text-slate-400',
  },
}

function ZBar({ z }: { z: number | null }) {
  if (z === null) return null
  // 将 z 映射到 [-3, +3] 范围的百分比（50% = 中性）
  const pct = Math.min(Math.max(((z + 3) / 6) * 100, 2), 98)
  return (
    <div className="relative h-1.5 rounded-full bg-white/20 mt-2 mb-1 overflow-visible">
      <div
        className="absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-white shadow-sm border-2 border-white/50"
        style={{ left: `${pct}%`, transform: 'translate(-50%, -50%)' }}
      />
      {/* 中性基准线 */}
      <div className="absolute top-0 bottom-0 w-px bg-white/40" style={{ left: '50%' }} />
    </div>
  )
}

function SectorCard({ sv }: { sv: SectorValuation }) {
  const key = (sv.label_en || 'insufficient') as LabelEn
  const style = LABEL_STYLE[key] ?? LABEL_STYLE.insufficient
  const zStr = sv.z_score !== null ? (sv.z_score >= 0 ? '+' : '') + sv.z_score.toFixed(2) : '—'
  const peStr = sv.current_pe !== null ? sv.current_pe.toFixed(1) : '—'
  const meanStr = sv.hist_mean !== null ? sv.hist_mean.toFixed(1) : '—'

  return (
    <div className={`rounded-xl p-4 flex flex-col gap-1 ${style.bg} ${style.text} shadow-sm`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-bold text-base leading-tight">{sv.sector_cn}</div>
          <div className="text-xs opacity-60 mt-0.5">{sv.sector}</div>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium whitespace-nowrap ${style.badge}`}>
          {sv.label}
        </span>
      </div>

      <div className="text-3xl font-mono font-extrabold tracking-tight mt-1">{zStr}σ</div>

      <ZBar z={sv.z_score} />

      <div className="flex items-center justify-between text-xs opacity-70 mt-0.5">
        <span>当前 PE <span className="font-semibold opacity-100">{peStr}</span></span>
        <span>历史均值 <span className="font-semibold opacity-100">{meanStr}</span></span>
      </div>
      {sv.hist_std !== null && (
        <div className="text-xs opacity-50">±1σ = {sv.hist_std.toFixed(1)}</div>
      )}
    </div>
  )
}

const LABEL_ORDER: Record<LabelEn, number> = {
  extreme_undervalue: 0,
  undervalue: 1,
  neutral: 2,
  overvalue: 3,
  extreme_overvalue: 4,
  insufficient: 5,
}

export default function SectorValuationGrid({ data }: Props) {
  const sorted = [...data.sectors].sort((a, b) => {
    const ak = (a.label_en || 'insufficient') as LabelEn
    const bk = (b.label_en || 'insufficient') as LabelEn
    const orderDiff = (LABEL_ORDER[ak] ?? 5) - (LABEL_ORDER[bk] ?? 5)
    if (orderDiff !== 0) return orderDiff
    // 同类按 z-score 升序（低估越深越靠前）
    const az = a.z_score ?? 0
    const bz = b.z_score ?? 0
    return az - bz
  })

  const withData = sorted.filter((s) => s.z_score !== null)
  const undervalued = withData.filter((s) => (s.z_score ?? 0) < -1)
  const overvalued = withData.filter((s) => (s.z_score ?? 0) >= 1)

  return (
    <div className="space-y-4">
      {/* 顶部摘要 */}
      <div className="flex items-center gap-4 px-4 py-3 rounded-xl border border-gray-200 bg-gray-50 flex-wrap text-xs text-gray-500">
        <span>数据截至 <span className="font-semibold text-gray-700">{data.as_of || '—'}</span></span>
        <span className="text-gray-300">·</span>
        <span>历史基准 <span className="font-semibold text-gray-700">10 年</span>（季度 PE）</span>
        <span className="text-gray-300">·</span>
        <span>数据来源：S&P 500 GICS 行业</span>
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

      {/* 图例 */}
      <div className="flex items-center gap-1.5 text-xs text-gray-400 px-1">
        <span className="px-2 py-0.5 rounded-full bg-blue-700 text-white text-xs">极度低估 z≤-2σ</span>
        <span className="px-2 py-0.5 rounded-full bg-blue-400 text-white text-xs">低估 -2~-1σ</span>
        <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 text-xs border">中性 -1~+1σ</span>
        <span className="px-2 py-0.5 rounded-full bg-orange-400 text-white text-xs">高估 +1~+2σ</span>
        <span className="px-2 py-0.5 rounded-full bg-red-600 text-white text-xs">极度高估 ≥+2σ</span>
      </div>

      {/* 卡片网格 */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {sorted.map((sv) => (
          <SectorCard key={sv.sector} sv={sv} />
        ))}
      </div>

      {/* 底部说明 */}
      <p className="text-xs text-gray-400 px-1">
        <span className="font-medium text-gray-500">z-score</span> = (当前 PE − 10年历史均值) ÷ 标准差。
        圆点越靠左代表估值越低，越靠右代表估值越高。中性区间（±1σ）涵盖约 68% 的历史观测值。
      </p>
    </div>
  )
}
