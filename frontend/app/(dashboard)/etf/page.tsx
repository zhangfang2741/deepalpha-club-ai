'use client'

import { useEffect, useState } from 'react'
import { fetchETFHeatmap } from '@/lib/api/etf'
import type { HeatmapResponse, Granularity } from '@/lib/api/etf'
import { useETFStore } from '@/lib/store/etf'
import GranularityToggle from '@/components/etf/GranularityToggle'
import ETFHeatmapTable from '@/components/etf/ETFHeatmapTable'
import Spinner from '@/components/ui/Spinner'

export default function ETFPage() {
  const { granularity, days, setGranularity } = useETFStore()
  const [data, setData] = useState<HeatmapResponse | null>(null)
  // 初始为 true，后续由事件处理器在切换粒度时重置为 true
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    fetchETFHeatmap(granularity, days)
      .then((result) => {
        if (!cancelled) {
          setData(result)
          setError('')
        }
      })
      .catch(() => {
        if (!cancelled) setError('数据加载失败，请重试')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [granularity, days])

  const handleGranularityChange = (g: Granularity) => {
    setLoading(true)
    setGranularity(g)
  }

  const handleRetry = () => {
    setLoading(true)
    setError('')
    fetchETFHeatmap(granularity, days)
      .then((result) => {
        setData(result)
      })
      .catch(() => setError('数据加载失败，请重试'))
      .finally(() => setLoading(false))
  }

  return (
    <div>
      {/* 页头 */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-gray-900">ETF 资金流</h1>
        <GranularityToggle
          value={granularity}
          onChange={handleGranularityChange}
          disabled={loading}
        />
      </div>

      {/* 说明文字 */}
      <p className="text-sm text-gray-500 mb-4">
        资金流强度基于 CLV × 价格 × 成交量计算，经 Z-score 标准化。
        红色表示资金流入，绿色表示资金流出，颜色越深强度越大。
      </p>

      {/* 错误状态 */}
      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center justify-between">
          <span className="text-sm text-red-600">{error}</span>
          <button
            onClick={handleRetry}
            className="text-sm text-red-600 font-medium hover:text-red-800 underline"
          >
            重试
          </button>
        </div>
      )}

      {/* 初始加载 */}
      {loading && !data && (
        <div className="rounded-xl border border-gray-200 bg-white flex items-center justify-center h-64">
          <Spinner size={40} />
        </div>
      )}

      {/* 热力图表格（切换粒度时叠遮罩） */}
      {data && (
        <div className="relative">
          <ETFHeatmapTable data={data} granularity={granularity} />
          {loading && (
            <div className="absolute inset-0 bg-white/60 rounded-xl flex items-center justify-center pointer-events-none">
              <Spinner size={40} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
