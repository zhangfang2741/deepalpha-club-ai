'use client'

import { useEffect, useState } from 'react'
import { fetchETFHeatmap } from '@/lib/api/etf'
import type { HeatmapResponse, Granularity } from '@/lib/api/etf'
import { useETFStore } from '@/lib/store/etf'
import GranularityToggle from '@/components/etf/GranularityToggle'
import ETFHeatmapTable from '@/components/etf/ETFHeatmapTable'
import Spinner from '@/components/ui/Spinner'
import DashboardShell from '@/components/layout/DashboardShell'

export default function ETFPage() {
  const { granularity, days, setGranularity } = useETFStore()

  // 热力图状态
  const [heatmapData, setHeatmapData] = useState<HeatmapResponse | null>(null)
  const [heatmapLoading, setHeatmapLoading] = useState(true)
  const [heatmapError, setHeatmapError] = useState('')

  // 热力图加载
  useEffect(() => {
    let cancelled = false

    setHeatmapLoading(true)
    fetchETFHeatmap(granularity, days)
      .then((result) => {
        if (!cancelled) {
          setHeatmapData(result)
          setHeatmapError('')
        }
      })
      .catch(() => {
        if (!cancelled) setHeatmapError('数据加载失败，请重试')
      })
      .finally(() => {
        if (!cancelled) setHeatmapLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [granularity, days])

  const handleGranularityChange = (g: Granularity) => {
    setHeatmapLoading(true)
    setGranularity(g)
  }

  const handleHeatmapRetry = () => {
    setHeatmapLoading(true)
    setHeatmapError('')
    fetchETFHeatmap(granularity, days)
      .then((result) => setHeatmapData(result))
      .catch(() => setHeatmapError('数据加载失败，请重试'))
      .finally(() => setHeatmapLoading(false))
  }

  return (
    <DashboardShell>
      {/* 页头 */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-gray-900">ETF 资金流</h1>
        <GranularityToggle
          value={granularity}
          onChange={handleGranularityChange}
          disabled={heatmapLoading}
        />
      </div>

      <p className="text-sm text-gray-500 mb-4">
        资金流强度基于 CLV × 价格 × 成交量计算，经 Z-score 标准化。
        红色表示资金流入，绿色表示资金流出，颜色越深强度越大。
      </p>

      {heatmapError && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center justify-between">
          <span className="text-sm text-red-600">{heatmapError}</span>
          <button
            onClick={handleHeatmapRetry}
            className="text-sm text-red-600 font-medium hover:text-red-800 underline"
          >
            重试
          </button>
        </div>
      )}

      {heatmapLoading && !heatmapData && (
        <div className="rounded-xl border border-gray-200 bg-white flex items-center justify-center h-64">
          <Spinner size={40} />
        </div>
      )}

      {heatmapData && (
        <div className="relative">
          <ETFHeatmapTable data={heatmapData} granularity={granularity} />
          {heatmapLoading && (
            <div className="absolute inset-0 bg-white/60 rounded-xl flex items-center justify-center pointer-events-none">
              <Spinner size={40} />
            </div>
          )}
        </div>
      )}
    </DashboardShell>
  )
}
