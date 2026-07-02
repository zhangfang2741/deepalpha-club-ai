'use client'

import { useState } from 'react'
import Link from 'next/link'
import { TrendingUp, Search, Loader2, Info } from 'lucide-react'
import DashboardShell from '@/components/layout/DashboardShell'
import PriceTargetChart from '@/components/analyst_upgrades/PriceTargetChart'
import { fetchCustomPriceTargetHistory } from '@/lib/api/analyst_upgrade'
import type { PriceTargetPoint, StockPricePoint } from '@/lib/api/analyst_upgrade'

// 返回 YYYY-MM-DD 格式的本地日期字符串
function toDateInput(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// 默认区间：当前时间往前两年
function defaultRange(): { start: string; end: string } {
  const now = new Date()
  const start = new Date(now.getFullYear() - 2, now.getMonth(), now.getDate())
  return { start: toDateInput(start), end: toDateInput(now) }
}

export default function CustomPriceTargetPage() {
  const initial = defaultRange()
  const [symbol, setSymbol] = useState('')
  const [start, setStart] = useState(initial.start)
  const [end, setEnd] = useState(initial.end)
  const [points, setPoints] = useState<PriceTargetPoint[] | null>(null)
  const [pricePoints, setPricePoints] = useState<StockPricePoint[]>([])
  const [queried, setQueried] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const query = () => {
    const sym = symbol.trim().toUpperCase()
    if (!sym) {
      setError('请输入美股股票代码')
      return
    }
    if (start > end) {
      setError('起始日期不能晚于结束日期')
      return
    }
    setLoading(true)
    setError('')
    fetchCustomPriceTargetHistory(sym, start, end)
      .then((res) => {
        setPoints(res.points)
        setPricePoints(res.price_points ?? [])
        setQueried(sym)
      })
      .catch(() => setError('数据加载失败，请检查股票代码是否正确后重试'))
      .finally(() => setLoading(false))
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') query()
  }

  return (
    <DashboardShell>
      <div className="space-y-6">
        {/* 页头 */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <TrendingUp className="w-5 h-5 text-blue-600" />
              <h1 className="text-xl font-bold text-gray-900">分析师持续上调</h1>
            </div>
            <p className="text-sm text-gray-500">
              自定义查询：输入美股股票并选定时间区间，查看每月分析师平均目标价与股价走势
            </p>
          </div>
        </div>

        {/* 指数切换标签 */}
        <div className="flex gap-1 border-b border-gray-200">
          <Link
            href="/analyst-upgrades"
            className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 transition-colors"
          >
            纳斯达克 100
          </Link>
          <Link
            href="/analyst-upgrades/sp500"
            className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 transition-colors"
          >
            标普 500
          </Link>
          <span className="px-4 py-2 text-sm font-medium text-blue-600 border-b-2 border-blue-600 -mb-px">
            自定义
          </span>
        </div>

        {/* 查询表单 */}
        <div className="flex flex-wrap items-end gap-3 bg-gray-50 rounded-lg px-4 py-4">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">股票代码</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="如 AAPL"
              className="w-32 px-3 py-1.5 text-sm border border-gray-300 rounded-lg uppercase focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">起始日期</label>
            <input
              type="date"
              value={start}
              max={end}
              onChange={(e) => setStart(e.target.value)}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">结束日期</label>
            <input
              type="date"
              value={end}
              min={start}
              onChange={(e) => setEnd(e.target.value)}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <button
            onClick={query}
            disabled={loading}
            className="flex items-center gap-1.5 px-4 py-1.5 text-sm text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-40 transition-colors"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
            查询
          </button>
          <span className="flex items-center gap-1 text-xs text-gray-400 ml-auto">
            <Info className="w-3 h-3" />
            默认区间为近两年，数据 12h 缓存
          </span>
        </div>

        {/* 内容区 */}
        {error && (
          <div className="text-center py-12 text-red-500 text-sm">{error}</div>
        )}

        {!error && loading && (
          <div className="flex flex-col items-center justify-center py-24 gap-3 text-gray-400">
            <Loader2 className="w-6 h-6 animate-spin" />
            <p className="text-sm">正在拉取 {symbol.trim().toUpperCase()} 分析师目标价数据…</p>
          </div>
        )}

        {!error && !loading && points !== null && (
          <div className="bg-white border border-gray-100 rounded-2xl shadow-sm px-6 py-5 space-y-3">
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold text-gray-900">{queried}</span>
              <span className="text-xs text-gray-400">
                {start} ~ {end} · 按月聚合分析师平均目标价与月末股价
              </span>
            </div>
            {points.length > 0 ? (
              <PriceTargetChart points={points} pricePoints={pricePoints} />
            ) : (
              <div className="flex items-center justify-center h-60 text-gray-400 text-sm">
                该区间内暂无分析师目标价数据
              </div>
            )}
          </div>
        )}

        {!error && !loading && points === null && (
          <div className="text-center py-16 text-gray-400 text-sm">
            输入美股股票代码并选择时间区间后点击「查询」
          </div>
        )}

        {/* 方法说明 */}
        <div className="text-xs text-gray-400 bg-gray-50 rounded-lg p-4 space-y-1">
          <p><span className="font-medium text-gray-500">目标价（蓝）：</span>所选区间内每个月所有分析师给出目标价的算术平均值</p>
          <p><span className="font-medium text-gray-500">股价（橙）：</span>每月最后一个交易日的收盘价</p>
          <p><span className="font-medium text-gray-500">默认区间：</span>当前时间往前两年</p>
          <p><span className="font-medium text-gray-500">数据源：</span>Financial Modeling Prep (FMP)</p>
        </div>
      </div>
    </DashboardShell>
  )
}
