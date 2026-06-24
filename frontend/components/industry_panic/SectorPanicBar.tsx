'use client'

import type { SectorPanic } from '@/lib/api/industry_panic'
import { getRsiColor, getRsiLevel } from '@/lib/constants/industryPanic'

interface Props {
  sectors: SectorPanic[]
  selectedSymbol: string
  onSelect: (sector: SectorPanic) => void
}

export default function SectorPanicBar({ sectors, selectedSymbol, onSelect }: Props) {
  // RSI 越低越弱势，排在前面
  const sorted = [...sectors].sort(
    (a, b) => (a.current_rsi ?? 50) - (b.current_rsi ?? 50)
  )

  return (
    <div className="space-y-2">
      {sorted.map((s) => {
        const rsi = s.current_rsi ?? 50
        const color = getRsiColor(rsi)
        const level = getRsiLevel(rsi)
        const isSelected = s.symbol === selectedSymbol

        return (
          <button
            key={s.symbol}
            onClick={() => onSelect(s)}
            className={[
              'w-full flex items-center gap-3 px-3 py-2.5 rounded-xl border transition-all text-left group',
              isSelected
                ? 'border-gray-300 bg-white shadow-sm'
                : 'border-transparent hover:border-gray-200 hover:bg-white/60',
            ].join(' ')}
          >
            {/* 行业名 */}
            <div className="w-24 shrink-0 text-right">
              <div className="text-xs font-semibold text-gray-700 leading-tight">
                {s.sector_cn}
              </div>
              <div className="text-[10px] text-gray-400 font-mono">{s.symbol}</div>
            </div>

            {/* 进度条：RSI 0-100 */}
            <div className="flex-1 relative h-5 bg-gray-100 rounded-full overflow-hidden">
              <div
                className="absolute left-0 top-0 h-full rounded-full transition-all duration-500"
                style={{ width: `${rsi}%`, backgroundColor: color, opacity: 0.85 }}
              />
              {/* RSI 30 超卖线 */}
              <div className="absolute top-0 h-full w-px bg-red-300/60" style={{ left: '30%' }} />
              {/* RSI 50 中性基准线 */}
              <div className="absolute left-1/2 top-0 h-full w-px bg-gray-300/60" />
              {/* RSI 70 超买线 */}
              <div className="absolute top-0 h-full w-px bg-blue-300/60" style={{ left: '70%' }} />
            </div>

            {/* RSI 值 + 等级 */}
            <div className="w-24 shrink-0 flex items-center gap-2">
              <span className="text-sm font-bold tabular-nums w-8" style={{ color }}>
                {rsi.toFixed(1)}
              </span>
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded shrink-0 ${level.badgeClass}`}>
                {level.label}
              </span>
            </div>
          </button>
        )
      })}
    </div>
  )
}
