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

const LABEL_CONFIG: Record<LabelEn, { bg: string; text: string; border: string }> = {
  extreme_undervalue: { bg: 'bg-blue-700', text: 'text-white', border: 'border-blue-700' },
  undervalue:         { bg: 'bg-blue-500', text: 'text-white', border: 'border-blue-500' },
  neutral:            { bg: 'bg-slate-200', text: 'text-slate-700', border: 'border-slate-300' },
  overvalue:          { bg: 'bg-orange-500', text: 'text-white', border: 'border-orange-500' },
  extreme_overvalue:  { bg: 'bg-red-600', text: 'text-white', border: 'border-red-600' },
  insufficient:       { bg: 'bg-slate-100', text: 'text-slate-400', border: 'border-slate-200' },
}

const Z_COLOR: Record<LabelEn, string> = {
  extreme_undervalue: '#1d4ed8',
  undervalue:         '#3b82f6',
  neutral:            '#64748b',
  overvalue:          '#f97316',
  extreme_overvalue:  '#ef4444',
  insufficient:       '#94a3b8',
}

export default function SectorDetailPanel({ detail }: Props) {
  const key = (detail.label_en || 'insufficient') as LabelEn
  const cfg = LABEL_CONFIG[key] ?? LABEL_CONFIG.insufficient
  const zColor = Z_COLOR[key] ?? '#94a3b8'

  const zStr = detail.z_score !== null
    ? (detail.z_score >= 0 ? '+' : '') + detail.z_score.toFixed(2)
    : '—'

  const hasPE = detail.hist_pe.length >= 4 && detail.hist_mean !== null && detail.hist_std !== null

  return (
    <div className="space-y-5 h-full">
      {/* ETF 头部 */}
      <div className="flex items-start gap-4 pb-4 border-b border-slate-100">
        {/* 左：代码 + 名称 */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2.5 flex-wrap">
            <span className="text-2xl font-extrabold text-slate-900 font-mono tracking-tight">
              {detail.symbol}
            </span>
            <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${cfg.bg} ${cfg.text} ${cfg.border}`}>
              {detail.label}
            </span>
          </div>
          <div className="text-sm text-slate-500 mt-0.5 leading-tight">{detail.name}</div>
          <div className="flex items-center gap-4 mt-2 text-xs text-slate-400 flex-wrap">
            {detail.current_pe !== null && (
              <span>
                当前 PE{' '}
                <span className="font-bold text-slate-700 font-mono">{detail.current_pe.toFixed(2)}</span>
              </span>
            )}
            {detail.hist_mean !== null && (
              <span>
                历史均值{' '}
                <span className="font-bold text-slate-700 font-mono">{detail.hist_mean.toFixed(2)}</span>
              </span>
            )}
            {detail.hist_std !== null && (
              <span>
                ±1σ{' '}
                <span className="font-bold text-slate-700 font-mono">{detail.hist_std.toFixed(2)}</span>
              </span>
            )}
            <span>{detail.data_quarters} 个季度数据</span>
          </div>
        </div>

        {/* 右：z-score 大字 */}
        <div className="text-right flex-shrink-0">
          <div
            className="text-4xl font-extrabold font-mono tracking-tight leading-none"
            style={{ color: zColor }}
          >
            {zStr}σ
          </div>
          <div className="text-xs text-slate-400 mt-1">z-score</div>
        </div>
      </div>

      {/* PE 估值曲线 */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-sm font-bold text-slate-800">近 5 年季度 PE 走势</h4>
          <span className="text-xs text-slate-400">σ 区块 = ±1σ / ±2σ 历史分布</span>
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
          <div className="flex flex-col items-center justify-center h-52 rounded-xl border border-dashed border-slate-200 bg-slate-50">
            <div className="text-2xl mb-2">📊</div>
            <div className="text-sm text-slate-400 font-medium">暂无 PE 历史数据</div>
            <div className="text-xs text-slate-300 mt-1">该 ETF 可能不含 PE 指标（如商品、债券、加密类）</div>
          </div>
        )}
      </div>
    </div>
  )
}
