'use client'

import { useState } from 'react'
import type { UpgradeStock } from '@/lib/api/analyst_upgrade'
import Sparkline from './Sparkline'
import PriceTargetModal from './PriceTargetModal'

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

interface Props {
  stocks: UpgradeStock[]
}

export default function UpgradeTable({ stocks }: Props) {
  const [selected, setSelected] = useState<UpgradeStock | null>(null)

  return (
    <>
      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
        <table className="w-full text-left">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="py-3 pl-4 pr-2 text-xs font-medium text-gray-400 w-8">#</th>
              <th className="py-3 px-3 text-xs font-medium text-gray-500">代码 / 公司</th>
              <th className="py-3 px-3 text-xs font-medium text-gray-500 text-right">近月目标价</th>
              <th className="py-3 px-3 text-xs font-medium text-gray-500 text-right">月环比↑</th>
              <th className="py-3 px-3 text-xs font-medium text-gray-500 text-right hidden sm:table-cell">季环比↑</th>
              <th className="py-3 px-3 text-xs font-medium text-gray-500 text-right hidden md:table-cell">年环比↑</th>
              <th className="py-3 px-3 text-xs font-medium text-gray-500 text-right hidden lg:table-cell">报告机构</th>
              <th className="py-3 px-3 text-xs font-medium text-gray-500 text-center">目标价走势</th>
            </tr>
          </thead>
          <tbody>
            {stocks.map((stock, i) => (
              <tr
                key={stock.symbol}
                className="border-b border-gray-100 hover:bg-blue-50/40 transition-colors"
              >
                <td className="py-3 pl-4 pr-2 text-sm text-gray-400">{i + 1}</td>
                <td className="py-3 px-3">
                  <div className="font-semibold text-gray-900 text-sm">{stock.symbol}</div>
                  <div className="text-xs text-gray-400 truncate max-w-[140px]">{stock.name}</div>
                </td>
                <td className="py-3 px-3 text-right font-mono text-sm text-gray-800">
                  ${stock.last_month_target.toFixed(0)}
                </td>
                <td className="py-3 px-3 text-right">
                  <MomBadge value={stock.month_mom} />
                </td>
                <td className="py-3 px-3 text-right text-sm text-blue-600 font-medium hidden sm:table-cell">
                  +{stock.quarter_yoy.toFixed(1)}%
                </td>
                <td className="py-3 px-3 text-right text-sm text-purple-600 font-medium hidden md:table-cell">
                  {stock.year_vs_all > 0 ? '+' : ''}{stock.year_vs_all.toFixed(1)}%
                </td>
                <td className="py-3 px-3 text-right text-xs text-gray-400 hidden lg:table-cell">
                  {stock.last_month_count} 家
                </td>
                {/* 迷你趋势图 + 点击放大 */}
                <td className="py-3 px-3 text-center">
                  <button
                    onClick={() => setSelected(stock)}
                    title="点击查看大图"
                    className="group inline-flex items-center justify-center hover:opacity-80 transition-opacity cursor-zoom-in"
                  >
                    <Sparkline
                      values={
                        stock.recent_points.length >= 3
                          ? stock.recent_points.map((p) => p.avg_target)
                          : [stock.last_year_target, stock.last_quarter_target, stock.last_month_target]
                      }
                      width={120}
                      height={36}
                    />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected && (
        <PriceTargetModal
          stock={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  )
}
