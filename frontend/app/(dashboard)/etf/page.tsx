'use client'

import { useEffect, useState } from 'react'
import { fetchETFHeatmap, fetchETFDeviationScores } from '@/lib/api/etf'
import type { HeatmapResponse, Granularity, DeviationScoreResponse } from '@/lib/api/etf'
import { useETFStore } from '@/lib/store/etf'
import GranularityToggle from '@/components/etf/GranularityToggle'
import ETFHeatmapTable from '@/components/etf/ETFHeatmapTable'
import ETFDeviationTable from '@/components/etf/ETFDeviationTable'
import Spinner from '@/components/ui/Spinner'

type ActiveTab = 'heatmap' | 'deviation'

export default function ETFPage() {
  const { granularity, days, setGranularity } = useETFStore()
  const [activeTab, setActiveTab] = useState<ActiveTab>('heatmap')

  // 热力图状态
  const [heatmapData, setHeatmapData] = useState<HeatmapResponse | null>(null)
  const [heatmapLoading, setHeatmapLoading] = useState(true)
  const [heatmapError, setHeatmapError] = useState('')

  // 偏离分状态（懒加载：切换到该 Tab 时才加载）
  const [deviationData, setDeviationData] = useState<DeviationScoreResponse | null>(null)
  const [deviationLoading, setDeviationLoading] = useState(false)
  const [deviationError, setDeviationError] = useState('')

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

  // 偏离分懒加载：首次切换到 deviation Tab 时触发（deviationLoading 不放入依赖，避免触发 cleanup 取消请求）
  useEffect(() => {
    if (activeTab !== 'deviation' || deviationData !== null) return

    let cancelled = false
    setDeviationLoading(true)
    setDeviationError('')
    fetchETFDeviationScores(days)
      .then((result) => {
        if (!cancelled) {
          setDeviationData(result)
        }
      })
      .catch(() => {
        if (!cancelled) setDeviationError('偏离分数据加载失败，请重试')
      })
      .finally(() => {
        if (!cancelled) setDeviationLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [activeTab, days, deviationData])

  const handleGranularityChange = (g: Granularity) => {
    setHeatmapLoading(true)
    setGranularity(g)
    // 切换粒度时重置偏离分数据，等待重新加载
    setDeviationData(null)
  }

  const handleHeatmapRetry = () => {
    setHeatmapLoading(true)
    setHeatmapError('')
    fetchETFHeatmap(granularity, days)
      .then((result) => setHeatmapData(result))
      .catch(() => setHeatmapError('数据加载失败，请重试'))
      .finally(() => setHeatmapLoading(false))
  }

  const handleDeviationRetry = () => {
    setDeviationData(null)
    setDeviationError('')
  }

  return (
    <div>
      {/* 页头 */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-gray-900">ETF 资金流</h1>
        {activeTab === 'heatmap' && (
          <GranularityToggle
            value={granularity}
            onChange={handleGranularityChange}
            disabled={heatmapLoading}
          />
        )}
      </div>

      {/* 标签切换 */}
      <div className="flex gap-1 mb-4 border-b border-gray-200">
        {(['heatmap', 'deviation'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={[
              'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
              activeTab === tab
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700',
            ].join(' ')}
          >
            {tab === 'heatmap' ? '资金流热力图' : '偏离分析'}
          </button>
        ))}
      </div>

      {/* 热力图 Tab */}
      {activeTab === 'heatmap' && (
        <>
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
        </>
      )}

      {/* 偏离分 Tab */}
      {activeTab === 'deviation' && (
        <>
          <p className="text-sm text-gray-500 mb-4">
            衡量每只 ETF 在市场恐慌（FG&lt;45）或贪婪（FG&gt;55）期间相对于全市场均值的资金流偏离程度。
            红色=高于市场均值，绿色=低于市场均值。
          </p>

          {deviationError && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center justify-between">
              <span className="text-sm text-red-600">{deviationError}</span>
              <button
                onClick={handleDeviationRetry}
                className="text-sm text-red-600 font-medium hover:text-red-800 underline"
              >
                重试
              </button>
            </div>
          )}

          {deviationLoading && !deviationData && (
            <div className="rounded-xl border border-gray-200 bg-white flex items-center justify-center h-64">
              <Spinner size={40} />
            </div>
          )}

          {deviationData && (
            <ETFDeviationTable data={deviationData} />
          )}
        </>
      )}
    </div>
  )
}
