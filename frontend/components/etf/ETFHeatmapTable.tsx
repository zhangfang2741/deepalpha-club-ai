'use client'

import { useState, Fragment } from 'react'
import type { HeatmapResponse, HeatmapCell } from '@/lib/api/etf'

interface ETFHeatmapTableProps {
  data: HeatmapResponse
}

function intensityStyle(intensity: number | null): React.CSSProperties {
  if (intensity === null) return { backgroundColor: '#f9fafb' }
  const alpha = Math.min(Math.abs(intensity) / 3, 1)
  const color =
    intensity > 0
      ? `rgba(239, 68, 68, ${alpha})`
      : `rgba(34, 197, 94, ${alpha})`
  return { backgroundColor: color }
}

function Cell({ cell }: { cell: HeatmapCell }) {
  return (
    <td
      className="px-2 py-1.5 text-center text-xs font-mono whitespace-nowrap border-r border-gray-100 min-w-[72px]"
      style={intensityStyle(cell.intensity)}
    >
      {cell.intensity !== null ? cell.intensity.toFixed(2) : '—'}
    </td>
  )
}

export default function ETFHeatmapTable({ data }: ETFHeatmapTableProps) {
  const [expandedSectors, setExpandedSectors] = useState<Set<string>>(new Set())

  const toggleSector = (sector: string) => {
    setExpandedSectors((prev) => {
      const next = new Set(prev)
      if (next.has(sector)) {
        next.delete(sector)
      } else {
        next.add(sector)
      }
      return next
    })
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
      <table
        className="border-collapse text-sm"
        style={{ minWidth: `${280 + data.date_labels.length * 72}px` }}
      >
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200">
            <th className="sticky left-0 z-20 bg-gray-50 px-4 py-2.5 text-left font-semibold text-gray-700 border-r border-gray-200 min-w-[200px]">
              板块/ETF
            </th>
            <th className="sticky left-[200px] z-20 bg-gray-50 px-3 py-2.5 text-left font-semibold text-gray-700 border-r border-gray-200 min-w-[80px]">
              Ticker
            </th>
            {data.date_labels.map((label) => (
              <th
                key={label}
                className="px-2 py-2.5 text-center font-medium text-gray-500 border-r border-gray-100 min-w-[72px] whitespace-nowrap"
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.sectors.map((sector) => {
            const isExpanded = expandedSectors.has(sector.sector)
            return (
              <Fragment key={sector.sector}>
                {/* 板块汇总行 */}
                <tr
                  className="border-b border-gray-200 cursor-pointer hover:bg-gray-50 transition-colors"
                  onClick={() => toggleSector(sector.sector)}
                >
                  <td className="sticky left-0 z-10 bg-white px-4 py-2 font-semibold text-gray-800 border-r border-gray-200">
                    <span className="mr-2 text-gray-400 text-xs">
                      {isExpanded ? '▼' : '▶'}
                    </span>
                    {sector.sector}
                  </td>
                  <td className="sticky left-[200px] z-10 bg-white px-3 py-2 text-gray-400 text-xs border-r border-gray-200">
                    {sector.etfs.length} 只
                  </td>
                  {sector.avg_cells.map((cell) => (
                    <Cell key={cell.date} cell={cell} />
                  ))}
                </tr>

                {/* ETF 明细行 */}
                {isExpanded &&
                  sector.etfs.map((etf) => (
                    <tr
                      key={etf.symbol}
                      className="border-b border-gray-100 hover:bg-gray-50 transition-colors"
                    >
                      <td className="sticky left-0 z-10 bg-white px-4 py-1.5 text-gray-600 text-xs border-r border-gray-200 pl-8 truncate max-w-[200px]">
                        {etf.name}
                      </td>
                      <td className="sticky left-[200px] z-10 bg-white px-3 py-1.5 text-gray-700 font-mono text-xs font-medium border-r border-gray-200">
                        {etf.symbol}
                      </td>
                      {etf.cells.map((cell) => (
                        <Cell key={cell.date} cell={cell} />
                      ))}
                    </tr>
                  ))}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
