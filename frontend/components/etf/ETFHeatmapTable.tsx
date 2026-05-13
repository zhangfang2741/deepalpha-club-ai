'use client'

import { useState, Fragment } from 'react'
import type { HeatmapResponse, HeatmapCell, HeatmapSectorGroup, Granularity } from '@/lib/api/etf'
import ETFCandleModal from '@/components/etf/ETFCandleModal'

interface ETFHeatmapTableProps {
  data: HeatmapResponse
  granularity: Granularity
}

type SortKey = string
type SortDir = 'asc' | 'desc'

// sqrt 曲线 + 最低保底透明度，确保小值（周/月）也清晰可见
function intensityStyle(intensity: number | null): React.CSSProperties {
  if (intensity === null || Math.abs(intensity) < 0.01) {
    return { backgroundColor: '#f8fafc' }
  }
  const abs = Math.abs(intensity)
  const alpha = Math.min(0.22 + 0.78 * Math.sqrt(abs / 3), 1)

  if (intensity > 0) {
    // 流入：红色，高 alpha 时文字用白色提升对比
    return {
      backgroundColor: `rgba(239, 68, 68, ${alpha})`,
      color: alpha > 0.55 ? '#fff' : '#1e293b',
    }
  } else {
    // 流出：绿色，深绿背景用深色文字
    return {
      backgroundColor: `rgba(22, 163, 74, ${alpha})`,
      color: alpha > 0.55 ? '#fff' : '#1e293b',
    }
  }
}

function Cell({ cell }: { cell: HeatmapCell }) {
  const style = intensityStyle(cell.intensity)
  return (
    <td
      className="px-2 py-2 text-center text-xs font-mono whitespace-nowrap border-r border-gray-100 min-w-[72px] transition-colors"
      style={style}
    >
      {cell.intensity !== null ? cell.intensity.toFixed(2) : '—'}
    </td>
  )
}

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <span className="ml-1 text-gray-300 text-[10px]">⇅</span>
  return <span className="ml-1 text-blue-500 text-[10px]">{dir === 'asc' ? '↑' : '↓'}</span>
}

function getCellIntensity(cells: HeatmapCell[], label: string): number {
  return cells.find((c) => c.date === label)?.intensity ?? -Infinity
}

function sortSectors(
  sectors: HeatmapSectorGroup[],
  sortKey: SortKey,
  sortDir: SortDir,
): HeatmapSectorGroup[] {
  return [...sectors].sort((a, b) => {
    const va = getCellIntensity(a.avg_cells, sortKey)
    const vb = getCellIntensity(b.avg_cells, sortKey)
    return sortDir === 'asc' ? va - vb : vb - va
  })
}

export default function ETFHeatmapTable({ data, granularity }: ETFHeatmapTableProps) {
  const [expandedSectors, setExpandedSectors] = useState<Set<string>>(new Set())
  const [sortKey, setSortKey] = useState<SortKey | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [selectedETF, setSelectedETF] = useState<{ symbol: string; name: string } | null>(null)

  const toggleSector = (sector: string) => {
    setExpandedSectors((prev) => {
      const next = new Set(prev)
      if (next.has(sector)) next.delete(sector)
      else next.add(sector)
      return next
    })
  }

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const sortedSectors = sortKey
    ? sortSectors(data.sectors, sortKey, sortDir)
    : data.sectors

  return (
    <>
      {selectedETF && (
        <ETFCandleModal
          symbol={selectedETF.symbol}
          name={selectedETF.name}
          granularity={granularity}
          onClose={() => setSelectedETF(null)}
        />
      )}

      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
        <table
          className="border-collapse text-sm w-full"
          style={{ minWidth: `${280 + data.date_labels.length * 72}px` }}
        >
          <thead>
            <tr className="bg-slate-50 border-b-2 border-gray-200">
              <th className="sticky left-0 z-20 bg-slate-50 px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider border-r border-gray-200 min-w-[200px]">
                板块 / ETF
              </th>
              <th className="sticky left-[200px] z-20 bg-slate-50 px-3 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider border-r border-gray-200 min-w-[80px]">
                Ticker
              </th>
              {data.date_labels.map((label) => (
                <th
                  key={label}
                  className="px-2 py-3 text-center text-xs font-medium text-gray-500 border-r border-gray-100 min-w-[72px] whitespace-nowrap cursor-pointer select-none hover:bg-blue-50 hover:text-blue-600 transition-colors"
                  onClick={() => handleSort(label)}
                >
                  {label}
                  <SortIcon active={sortKey === label} dir={sortDir} />
                </th>
              ))}
            </tr>
          </thead>

          <tbody className="divide-y divide-gray-100">
            {sortedSectors.map((sector, sectorIdx) => {
              const isExpanded = expandedSectors.has(sector.sector)
              const isEven = sectorIdx % 2 === 0
              const sortedEtfs =
                sortKey && sortKey !== 'name'
                  ? [...sector.etfs].sort((a, b) => {
                      const va = getCellIntensity(a.cells, sortKey)
                      const vb = getCellIntensity(b.cells, sortKey)
                      return sortDir === 'asc' ? va - vb : vb - va
                    })
                  : sector.etfs

              return (
                <Fragment key={sector.sector}>
                  {/* 板块汇总行 */}
                  <tr
                    className={`cursor-pointer hover:bg-blue-50/60 transition-colors ${isEven ? 'bg-white' : 'bg-slate-50/40'}`}
                    onClick={() => toggleSector(sector.sector)}
                  >
                    <td className={`sticky left-0 z-10 px-4 py-2.5 font-semibold text-gray-800 border-r border-gray-200 ${isEven ? 'bg-white' : 'bg-slate-50/80'}`}>
                      <div className="flex items-center gap-2">
                        <span className={`text-[10px] transition-transform duration-200 text-gray-400 ${isExpanded ? 'rotate-90' : ''}`}>▶</span>
                        <span className="text-sm">{sector.sector}</span>
                      </div>
                    </td>
                    <td className={`sticky left-[200px] z-10 px-3 py-2.5 text-gray-400 text-xs border-r border-gray-200 ${isEven ? 'bg-white' : 'bg-slate-50/80'}`}>
                      {sector.etfs.length} 只
                    </td>
                    {sector.avg_cells.map((cell) => (
                      <Cell key={cell.date} cell={cell} />
                    ))}
                  </tr>

                  {/* ETF 明细行 */}
                  {isExpanded &&
                    sortedEtfs.map((etf) => (
                      <tr
                        key={etf.symbol}
                        className="border-b border-gray-100 hover:bg-blue-50 transition-colors cursor-pointer bg-white"
                        onClick={() => setSelectedETF({ symbol: etf.symbol, name: etf.name })}
                      >
                        <td className="sticky left-0 z-10 bg-white px-4 py-2 text-gray-600 text-xs border-r border-gray-200 hover:text-blue-600 transition-colors">
                          <span className="pl-5 block truncate max-w-[170px]">{etf.name}</span>
                        </td>
                        <td className="sticky left-[200px] z-10 bg-white px-3 py-2 text-blue-500 font-mono text-xs font-medium border-r border-gray-200 underline decoration-dotted underline-offset-2">
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
    </>
  )
}
