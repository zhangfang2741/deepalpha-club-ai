'use client'

import type { ETFValuationDetail } from '@/lib/api/valuation'
import SectorPEChart from './SectorPEChart'

interface Props {
  detail: ETFValuationDetail
}

type LabelEn =
  | 'extreme_undervalue'
  | 'undervalue'
  | 'neutral'
  | 'overvalue'
  | 'extreme_overvalue'
  | 'insufficient'

const LABEL_CONFIG: Record<LabelEn, { bg: string; text: string; ring: string; glow: string }> = {
  extreme_undervalue: { bg: 'bg-blue-700',   text: 'text-white',      ring: 'ring-blue-700',   glow: 'shadow-blue-200' },
  undervalue:         { bg: 'bg-blue-500',   text: 'text-white',      ring: 'ring-blue-400',   glow: 'shadow-blue-100' },
  neutral:            { bg: 'bg-slate-200',  text: 'text-slate-600',  ring: 'ring-slate-200',  glow: '' },
  overvalue:          { bg: 'bg-orange-500', text: 'text-white',      ring: 'ring-orange-400', glow: 'shadow-orange-100' },
  extreme_overvalue:  { bg: 'bg-red-600',    text: 'text-white',      ring: 'ring-red-500',    glow: 'shadow-red-100' },
  insufficient:       { bg: 'bg-slate-100',  text: 'text-slate-400',  ring: 'ring-slate-200',  glow: '' },
}

const Z_COLOR: Record<LabelEn, string> = {
  extreme_undervalue: '#1d4ed8',
  undervalue:         '#3b82f6',
  neutral:            '#64748b',
  overvalue:          '#f97316',
  extreme_overvalue:  '#ef4444',
  insufficient:       '#cbd5e1',
}

const GAUGE_BG: Record<LabelEn, string> = {
  extreme_undervalue: 'from-blue-50 to-blue-100/50',
  undervalue:         'from-blue-50/60 to-slate-50',
  neutral:            'from-slate-50 to-slate-50',
  overvalue:          'from-orange-50/60 to-slate-50',
  extreme_overvalue:  'from-red-50 to-red-100/50',
  insufficient:       'from-slate-50 to-slate-50',
}

export default function SectorDetailPanel({ detail }: Props) {
  const key = (detail.label_en || 'insufficient') as LabelEn
  const cfg = LABEL_CONFIG[key] ?? LABEL_CONFIG.insufficient
  const zColor = Z_COLOR[key] ?? '#cbd5e1'

  const zStr = detail.z_score !== null
    ? (detail.z_score >= 0 ? '+' : '') + detail.z_score.toFixed(2)
    : '—'

  const hasPE = detail.hist_pe.length >= 4 && detail.hist_mean !== null && detail.hist_std !== null

  return (
    <div className="space-y-4 h-full flex flex-col">
      {/* ETF 头部卡片 */}
      <div className={`rounded-xl bg-gradient-to-br ${GAUGE_BG[key]} border border-slate-100 px-4 py-3`}>
        <div className="flex items-start gap-4">
          {/* 左：代码 + 名称 + 指标行 */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className="text-xl font-extrabold text-slate-900 font-mono tracking-tight">
                {detail.symbol}
              </span>
              <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold ring-1 shadow-sm ${cfg.bg} ${cfg.text} ${cfg.ring} ${cfg.glow}`}>
                {detail.label}
              </span>
            </div>
            <div className="text-xs text-slate-500 mt-0.5 leading-snug truncate">{detail.name}</div>

            {/* 数据行 */}
            <div className="flex items-center gap-4 mt-2.5 flex-wrap">
              {detail.current_pe !== null && (
                <div className="flex flex-col">
                  <span className="text-[10px] text-slate-400">当前 PE</span>
                  <span className="text-sm font-bold text-slate-800 font-mono">{detail.current_pe.toFixed(2)}</span>
                </div>
              )}
              {detail.hist_mean !== null && (
                <div className="flex flex-col">
                  <span className="text-[10px] text-slate-400">5年均值</span>
                  <span className="text-sm font-bold text-slate-600 font-mono">{detail.hist_mean.toFixed(2)}</span>
                </div>
              )}
              {detail.hist_std !== null && (
                <div className="flex flex-col">
                  <span className="text-[10px] text-slate-400">±1σ</span>
                  <span className="text-sm font-bold text-slate-600 font-mono">{detail.hist_std.toFixed(2)}</span>
                </div>
              )}
              <div className="flex flex-col">
                <span className="text-[10px] text-slate-400">数据</span>
                <span className="text-sm font-bold text-slate-500 font-mono">{detail.data_quarters}Q</span>
              </div>
            </div>
          </div>

          {/* 右：z-score 大字 */}
          <div className="text-right shrink-0">
            <div
              className="text-4xl font-extrabold font-mono tracking-tighter leading-none"
              style={{ color: zColor }}
            >
              {zStr}
            </div>
            <div className="text-[10px] text-slate-400 mt-1 font-medium">z-score (σ)</div>
          </div>
        </div>
      </div>

      {/* PE 估值曲线 */}
      <div className="flex-1">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-xs font-bold text-slate-700">近 5 年季度 PE 走势</h4>
          <span className="text-[10px] text-slate-400 bg-slate-50 px-2 py-0.5 rounded-full border border-slate-100">
            ±1σ / ±2σ 历史区间
          </span>
        </div>
        {hasPE ? (
          <SectorPEChart
            histPE={detail.hist_pe}
            mean={detail.hist_mean as number}
            std={detail.hist_std as number}
            currentPE={detail.current_pe}
            label_en={detail.label_en}
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-52 rounded-xl border border-dashed border-slate-200 bg-slate-50/50">
            <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center mb-3">
              <svg className="w-5 h-5 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <div className="text-sm text-slate-400 font-medium">暂无 PE 历史数据</div>
            <div className="text-[11px] text-slate-300 mt-1">该 ETF 不含 PE 指标（如商品、债券、加密类）</div>
          </div>
        )}
      </div>
    </div>
  )
}
