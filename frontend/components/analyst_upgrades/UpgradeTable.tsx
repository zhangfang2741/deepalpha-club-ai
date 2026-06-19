'use client'

import { useState } from 'react'
import { ChevronDown, ChevronUp, TrendingUp, Loader2 } from 'lucide-react'
import type { UpgradeStock, PriceTargetHistoryResponse } from '@/lib/api/analyst_upgrade'
import { fetchPriceTargetHistory } from '@/lib/api/analyst_upgrade'
import PriceTargetChart from './PriceTargetChart'

function MomBadge({ value }: { value: number }) {
  const color =
    value >= 20 ? 'bg-green-100 text-green-700' :
    value >= 10 ? 'bg-blue-100 text-blue-700' :
    value >= 5  ? 'bg-sky-100 text-sky-700' :
                  'bg-gray-100 text-gray-600'
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${color}`}>
      +{value.toFixed(1)}%
    </span>
  )
}

interface RowProps {
  stock: UpgradeStock
  rank: number
}

function UpgradeRow({ stock, rank }: RowProps) {
  const [expanded, setExpanded] = useState(false)
  const [history, setHistory] = useState<PriceTargetHistoryResponse | null>(null)
  const [loading, setLoading] = useState(false)

  const toggle = async () => {
    if (!expanded && !history) {
      setLoading(true)
      try {
        const data = await fetchPriceTargetHistory(stock.symbol)
        setHistory(data)
      } catch {
        setHistory({ symbol: stock.symbol, quarters: [] })
      } finally {
        setLoading(false)
      }
    }
    setExpanded((v) => !v)
  }

  return (
    <>
      <tr
        className="border-b border-gray-100 hover:bg-blue-50/40 cursor-pointer transition-colors"
        onClick={toggle}
      >
        <td className="py-3 pl-4 pr-2 text-sm text-gray-400 w-8">{rank}</td>
        <td className="py-3 px-3">
          <div className="font-semibold text-gray-900 text-sm">{stock.symbol}</div>
          <div className="text-xs text-gray-400 truncate max-w-[140px]">{stock.name}</div>
        </td>
        <td className="py-3 px-3 text-xs text-gray-500 hidden md:table-cell">{stock.sector}</td>
        <td className="py-3 px-3 text-right font-mono text-sm text-gray-800">
          ${stock.last_month_target.toFixed(0)}
        </td>
        <td className="py-3 px-3 text-right">
          <MomBadge value={stock.month_mom} />
        </td>
        <td className="py-3 px-3 text-right text-sm text-blue-600 font-medium hidden sm:table-cell">
          +{stock.quarter_yoy.toFixed(1)}%
        </td>
        <td className="py-3 px-3 text-right text-xs text-gray-400 hidden lg:table-cell">
          {stock.last_month_count} 家
        </td>
        <td className="py-3 pr-4 text-gray-300">
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </td>
      </tr>

      {expanded && (
        <tr className="bg-blue-50/30">
          <td colSpan={8} className="px-6 py-4">
            <div className="mb-1 text-xs font-medium text-gray-500 uppercase tracking-wide">
              {stock.symbol} · 近 5 年分析师平均目标价（季度）
            </div>
            {loading ? (
              <div className="flex items-center gap-2 text-sm text-gray-400 h-40 justify-center">
                <Loader2 className="w-4 h-4 animate-spin" />
                加载中…
              </div>
            ) : history ? (
              <PriceTargetChart symbol={stock.symbol} quarters={history.quarters} />
            ) : null}

            <div className="mt-3 flex gap-6 text-xs text-gray-500">
              <span>季均 <span className="font-semibold text-gray-700">${stock.last_quarter_target.toFixed(0)}</span></span>
              <span>年均 <span className="font-semibold text-gray-700">${stock.last_year_target.toFixed(0)}</span></span>
              <span>历史均 <span className="font-semibold text-gray-700">${stock.all_time_target.toFixed(0)}</span></span>
              <span>年内↑ <span className="font-semibold text-green-600">+{stock.year_vs_all.toFixed(1)}%</span></span>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

interface Props {
  stocks: UpgradeStock[]
}

export default function UpgradeTable({ stocks }: Props) {
  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
      <table className="w-full text-left">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200">
            <th className="py-3 pl-4 pr-2 text-xs font-medium text-gray-400 w-8">#</th>
            <th className="py-3 px-3 text-xs font-medium text-gray-500">代码 / 公司</th>
            <th className="py-3 px-3 text-xs font-medium text-gray-500 hidden md:table-cell">板块</th>
            <th className="py-3 px-3 text-xs font-medium text-gray-500 text-right">近月目标价</th>
            <th className="py-3 px-3 text-xs font-medium text-gray-500 text-right">月环比↑</th>
            <th className="py-3 px-3 text-xs font-medium text-gray-500 text-right hidden sm:table-cell">季环比↑</th>
            <th className="py-3 px-3 text-xs font-medium text-gray-500 text-right hidden lg:table-cell">报告机构</th>
            <th className="py-3 pr-4 w-6" />
          </tr>
        </thead>
        <tbody>
          {stocks.map((stock, i) => (
            <UpgradeRow key={stock.symbol} stock={stock} rank={i + 1} />
          ))}
        </tbody>
      </table>
    </div>
  )
}
