'use client'

import { useEffect, useState } from 'react'
import { X, Loader2 } from 'lucide-react'
import PriceTargetChart from './PriceTargetChart'
import { fetchPriceTargetHistory } from '@/lib/api/analyst_upgrade'
import type { PriceTargetPoint, UpgradeStock } from '@/lib/api/analyst_upgrade'

/** 当 API 无历史数据时，用 stock 的 4 个汇总点生成合成月度走势 */
function makeSyntheticPoints(stock: UpgradeStock): PriceTargetPoint[] {
  const now = new Date()

  // 相对当前月份回退 n 个月，返回 "YYYY-MM" 标签
  const monthsAgo = (n: number): string => {
    const d = new Date(now.getFullYear(), now.getMonth() - n, 1)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
  }

  return [
    { label: monthsAgo(36), avg_target: stock.all_time_target, count: 0 },
    { label: monthsAgo(12), avg_target: stock.last_year_target, count: 0 },
    { label: monthsAgo(3), avg_target: stock.last_quarter_target, count: 0 },
    { label: monthsAgo(0), avg_target: stock.last_month_target, count: 0 },
  ].filter((pt) => pt.avg_target > 0)
}

interface Props {
  stock: UpgradeStock
  onClose: () => void
}

export default function PriceTargetModal({ stock, onClose }: Props) {
  const [points, setPoints] = useState<PriceTargetPoint[] | null>(null)
  const [synthetic, setSynthetic] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // 优先使用列表响应中嵌入的 recent_points（与 sparkline 阈值一致，同为 >= 3 点）
    if (stock.recent_points && stock.recent_points.length >= 3) {
      setPoints(stock.recent_points)
      setSynthetic(false)
      setLoading(false)
      return
    }

    fetchPriceTargetHistory(stock.symbol)
      .then((res) => {
        if (res.points.length > 1) {
          setPoints(res.points)
          setSynthetic(false)
        } else {
          setPoints(makeSyntheticPoints(stock))
          setSynthetic(true)
        }
      })
      .catch(() => {
        setPoints(makeSyntheticPoints(stock))
        setSynthetic(true)
      })
      .finally(() => setLoading(false))
  }, [stock])

  // ESC 关闭
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        {/* 头部 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold text-gray-900">{stock.symbol}</span>
              <span className="text-sm text-gray-500">{stock.name}</span>
            </div>
            <p className="text-xs text-gray-400 mt-0.5">近 5 年分析师平均目标价 · 按月聚合</p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 快速指标 */}
        <div className="grid grid-cols-4 gap-0 border-b border-gray-100">
          {[
            { label: '近月目标价', value: `$${stock.last_month_target.toFixed(0)}`, sub: `月环比 +${stock.month_mom.toFixed(1)}%`, color: 'text-green-600' },
            { label: '季均目标价', value: `$${stock.last_quarter_target.toFixed(0)}`, sub: `季环比 +${stock.quarter_yoy.toFixed(1)}%`, color: 'text-blue-600' },
            { label: '年均目标价', value: `$${stock.last_year_target.toFixed(0)}`, sub: `年环比 ${stock.year_vs_all > 0 ? '+' : ''}${stock.year_vs_all.toFixed(1)}%`, color: 'text-purple-600' },
            { label: '报告机构数', value: `${stock.last_month_count} 家`, sub: '近一个月', color: 'text-gray-600' },
          ].map((item) => (
            <div key={item.label} className="px-4 py-3 text-center border-r last:border-r-0 border-gray-100">
              <div className={`text-base font-bold ${item.color}`}>{item.value}</div>
              <div className="text-xs text-gray-400 mt-0.5">{item.label}</div>
              <div className="text-xs text-gray-400">{item.sub}</div>
            </div>
          ))}
        </div>

        {/* 图表区 */}
        <div className="px-6 py-5">
          {loading ? (
            <div className="flex items-center justify-center h-60 gap-2 text-gray-400 text-sm">
              <Loader2 className="w-4 h-4 animate-spin" />
              加载历史数据…
            </div>
          ) : points !== null ? (
            <PriceTargetChart points={points} synthetic={synthetic} />
          ) : null}
        </div>
      </div>
    </div>
  )
}
