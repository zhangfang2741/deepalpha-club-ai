'use client'

import { CSSProperties, useState } from 'react'
import type { DeviationScoreResponse, ETFDeviationScore, SectorDeviationGroup } from '@/lib/api/etf'
import { getRatingColor, getRatingLabel } from '@/lib/constants/fearGreed'

interface Props {
  data: DeviationScoreResponse
}

type SortKey = 'panic_score' | 'greed_score' | 'overall_score'
type SortDir = 'asc' | 'desc'

function deviationStyle(score: number | null): CSSProperties {
  if (score === null || Math.abs(score) < 0.001) return { color: '#94a3b8' }
  const alpha = Math.min(0.15 + 0.7 * Math.sqrt(Math.abs(score) / 2), 0.85)
  if (score > 0) {
    return {
      backgroundColor: `rgba(239,68,68,${alpha})`,
      color: alpha > 0.5 ? '#fff' : '#7f1d1d',
    }
  }
  return {
    backgroundColor: `rgba(34,197,94,${alpha})`,
    color: alpha > 0.5 ? '#fff' : '#14532d',
  }
}

function fmt(v: number | null): string {
  if (v === null) return '—'
  return (v >= 0 ? '+' : '') + v.toFixed(2)
}

function ScoreCell({ score }: { score: number | null }) {
  return (
    <td
      className="px-3 py-2 text-center text-xs font-mono font-semibold rounded"
      style={deviationStyle(score)}
    >
      {fmt(score)}
    </td>
  )
}

function SortHeader({
  label,
  sortKey,
  currentKey,
  direction,
  onClick,
}: {
  label: string
  sortKey: SortKey
  currentKey: SortKey
  direction: SortDir
  onClick: (k: SortKey) => void
}) {
  const active = sortKey === currentKey
  return (
    <th
      className="px-3 py-2 text-center text-xs font-semibold text-gray-600 cursor-pointer select-none hover:text-gray-900 whitespace-nowrap"
      onClick={() => onClick(sortKey)}
    >
      {label}
      <span className="ml-1 text-gray-400">
        {active ? (direction === 'desc' ? '↓' : '↑') : '↕'}
      </span>
    </th>
  )
}

function sortEtfs(etfs: ETFDeviationScore[], key: SortKey, dir: SortDir): ETFDeviationScore[] {
  return [...etfs].sort((a, b) => {
    const av = a[key]
    const bv = b[key]
    if (av === null && bv === null) return 0
    if (av === null) return 1
    if (bv === null) return -1
    return dir === 'desc' ? bv - av : av - bv
  })
}

function SectorRow({
  sector,
  expanded,
  onToggle,
  sortKey,
}: {
  sector: SectorDeviationGroup
  expanded: boolean
  onToggle: () => void
  sortKey: SortKey
}) {
  return (
    <tr
      className="bg-gray-50 border-t border-gray-200 cursor-pointer hover:bg-gray-100"
      onClick={onToggle}
    >
      <td className="px-3 py-2 text-xs font-bold text-gray-700 sticky left-0 bg-gray-50">
        <span className="mr-1">{expanded ? '▼' : '▶'}</span>
        {sector.sector}
        <span className="ml-2 text-gray-400 font-normal">({sector.etfs.length})</span>
      </td>
      <td className="px-3 py-2 text-center text-xs text-gray-400">—</td>
      <ScoreCell score={sector.avg_panic_score} />
      <td className="px-3 py-2 text-center text-xs text-gray-400">—</td>
      <ScoreCell score={sector.avg_greed_score} />
      <td className="px-3 py-2 text-center text-xs text-gray-400">—</td>
      <ScoreCell score={sector.avg_overall_score} />
    </tr>
  )
}

export default function ETFDeviationTable({ data }: Props) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [sortKey, setSortKey] = useState<SortKey>('overall_score')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const toggleSector = (sector: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(sector)) next.delete(sector)
      else next.add(sector)
      return next
    })
  }

  const fgColor = getRatingColor(data.fg_rating)
  const fgLabel = getRatingLabel(data.fg_rating)

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      {/* 顶部信息栏 */}
      <div className="flex items-center gap-4 px-4 py-3 border-b border-gray-100 bg-gray-50/50">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">当前市场情绪</span>
          <span
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold"
            style={{ backgroundColor: fgColor + '20', color: fgColor }}
          >
            <span className="text-sm font-extrabold">{Math.round(data.fg_score)}</span>
            <span>{fgLabel}</span>
          </span>
        </div>
        <span className="text-xs text-gray-400">·</span>
        <span className="text-xs text-gray-500">数据窗口：过去 {data.days} 个交易日</span>
        <div className="ml-auto flex items-center gap-3 text-xs text-gray-400">
          <span>
            <span
              className="inline-block w-3 h-3 rounded-sm mr-1 align-middle"
              style={{ backgroundColor: 'rgba(239,68,68,0.6)' }}
            />
            高于市场均值
          </span>
          <span>
            <span
              className="inline-block w-3 h-3 rounded-sm mr-1 align-middle"
              style={{ backgroundColor: 'rgba(34,197,94,0.6)' }}
            />
            低于市场均值
          </span>
        </div>
      </div>

      {/* 表格 */}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-gray-200 bg-white">
              <th className="px-3 py-2 text-left text-xs font-semibold text-gray-600 sticky left-0 bg-white min-w-[180px]">
                板块 / ETF
              </th>
              <th className="px-3 py-2 text-center text-xs font-semibold text-gray-600 min-w-[70px]">
                代码
              </th>
              <SortHeader
                label="恐慌偏离"
                sortKey="panic_score"
                currentKey={sortKey}
                direction={sortDir}
                onClick={handleSort}
              />
              <th className="px-3 py-2 text-center text-xs text-gray-400 font-normal">天数</th>
              <SortHeader
                label="贪婪偏离"
                sortKey="greed_score"
                currentKey={sortKey}
                direction={sortDir}
                onClick={handleSort}
              />
              <th className="px-3 py-2 text-center text-xs text-gray-400 font-normal">天数</th>
              <SortHeader
                label="综合偏离"
                sortKey="overall_score"
                currentKey={sortKey}
                direction={sortDir}
                onClick={handleSort}
              />
            </tr>
          </thead>
          <tbody>
            {data.sectors.map((sector) => {
              const isExpanded = !collapsed.has(sector.sector)
              const sortedEtfs = sortEtfs(sector.etfs, sortKey, sortDir)
              return [
                <SectorRow
                  key={`sector-${sector.sector}`}
                  sector={sector}
                  expanded={isExpanded}
                  onToggle={() => toggleSector(sector.sector)}
                  sortKey={sortKey}
                />,
                ...(isExpanded
                  ? sortedEtfs.map((etf) => (
                      <tr
                        key={etf.symbol}
                        className="border-t border-gray-100 hover:bg-gray-50"
                      >
                        <td className="px-3 py-1.5 text-xs text-gray-700 sticky left-0 bg-white pl-7">
                          {etf.name}
                        </td>
                        <td className="px-3 py-1.5 text-center text-xs text-gray-400 font-mono">
                          {etf.symbol}
                        </td>
                        <ScoreCell score={etf.panic_score} />
                        <td className="px-3 py-1.5 text-center text-xs text-gray-400">
                          {etf.panic_days > 0 ? etf.panic_days : '—'}
                        </td>
                        <ScoreCell score={etf.greed_score} />
                        <td className="px-3 py-1.5 text-center text-xs text-gray-400">
                          {etf.greed_days > 0 ? etf.greed_days : '—'}
                        </td>
                        <ScoreCell score={etf.overall_score} />
                      </tr>
                    ))
                  : []),
              ]
            })}
          </tbody>
        </table>
      </div>

      {/* 底部说明 */}
      <div className="px-4 py-3 border-t border-gray-100 bg-gray-50/50">
        <p className="text-xs text-gray-400">
          偏离分 = ETF 当日强度 − 全市场均值，正值表示该 ETF 资金流高于市场均值。
          恐慌期（FG&lt;45）正值意味抗跌，贪婪期（FG&gt;55）正值意味强势。
          天数为所选窗口内实际匹配的恐慌/贪婪交易日数量。
        </p>
      </div>
    </div>
  )
}
