'use client'

import type { SectorWithIndustries } from '@/lib/api/valuation'
import { zScoreToPanic, getPanicColor, getPanicLevel } from '@/lib/constants/industryPanic'

interface Props {
  sectors: SectorWithIndustries[]
  selectedSector: string
  onSelect: (sector: SectorWithIndustries) => void
}

export default function SectorPanicBar({ sectors, selectedSector, onSelect }: Props) {
  const sorted = [...sectors].sort((a, b) => {
    return zScoreToPanic(b.z_score) - zScoreToPanic(a.z_score)
  })

  return (
    <div className="space-y-2">
      {sorted.map((s) => {
        const panic = zScoreToPanic(s.z_score)
        const color = getPanicColor(panic)
        const level = getPanicLevel(panic)
        const isSelected = s.sector === selectedSector

        return (
          <button
            key={s.sector}
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
              {s.current_pe !== null && (
                <div className="text-[10px] text-gray-400 font-mono">
                  PE {s.current_pe.toFixed(1)}
                </div>
              )}
            </div>

            {/* 进度条 */}
            <div className="flex-1 relative h-5 bg-gray-100 rounded-full overflow-hidden">
              <div
                className="absolute left-0 top-0 h-full rounded-full transition-all duration-500"
                style={{
                  width: `${panic}%`,
                  backgroundColor: color,
                  opacity: 0.85,
                }}
              />
              {/* 中性线 */}
              <div className="absolute left-1/2 top-0 h-full w-px bg-gray-300/60" />
            </div>

            {/* 分值 + 等级 */}
            <div className="w-24 shrink-0 flex items-center gap-2">
              <span
                className="text-sm font-bold tabular-nums w-8"
                style={{ color }}
              >
                {Math.round(panic)}
              </span>
              <span
                className={`text-[10px] font-bold px-1.5 py-0.5 rounded shrink-0 ${level.badgeClass}`}
              >
                {level.label}
              </span>
            </div>
          </button>
        )
      })}
    </div>
  )
}
