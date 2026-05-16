'use client'

import { useEffect, useState } from 'react'
import { fetchETFHeatmap, fetchETFDeviationScores } from '@/lib/api/etf'
import { fetchSectorValuations } from '@/lib/api/valuation'
import type { HeatmapResponse, Granularity, DeviationScoreResponse } from '@/lib/api/etf'
import type { SectorValuationResponse } from '@/lib/api/valuation'
import { useETFStore } from '@/lib/store/etf'
import GranularityToggle from '@/components/etf/GranularityToggle'
import ETFHeatmapTable from '@/components/etf/ETFHeatmapTable'
import ETFDeviationTable from '@/components/etf/ETFDeviationTable'
import SectorValuationGrid from '@/components/valuation/SectorValuationGrid'
import Spinner from '@/components/ui/Spinner'
import DashboardShell from '@/components/layout/DashboardShell'

type ActiveTab = 'heatmap' | 'deviation' | 'valuation'

export default function ETFPage() {
  const { granularity, days, setGranularity } = useETFStore()
  const [activeTab, setActiveTab] = useState<ActiveTab>('heatmap')

  // 热力图状态
  const [heatmapData, setHeatmapData] = useState<HeatmapResponse | null>(null)
  const [heatmapLoading, setHeatmapLoading] = useState(true)
  const [heatmapError, setHeatmapError] = useState('')

  // 偏离分状态（懒加载）
  const [deviationData, setDeviationData] = useState<DeviationScoreResponse | null>(null)
  const [deviationLoading, setDeviationLoading] = useState(false)
  const [deviationError, setDeviationError] = useState('')

  // 行业估值状态（懒加载）
  const [valuationData, setValuationData] = useState<SectorValuationResponse | null>(null)
  const [valuationLoading, setValuationLoading] = useState(false)
  const [valuationError, setValuationError] = useState('')

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

  // 偏离分懒加载
  useEffect(() => {
    if (activeTab !== 'deviation' || deviationData !== null) return

    let cancelled = false
    setDeviationLoading(true)
    setDeviationError('')
    fetchETFDeviationScores(days)
      .then((result) => {
        if (!cancelled) setDeviationData(result)
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

  // 行业估值懒加载（不依赖 days，数据固定为 10 年季度）
  useEffect(() => {
    if (activeTab !== 'valuation' || valuationData !== null) return

    let cancelled = false
    setValuationLoading(true)
    setValuationError('')
    fetchSectorValuations()
      .then((result) => {
        if (!cancelled) setValuationData(result)
      })
      .catch(() => {
        if (!cancelled) setValuationError('估值数据加载失败，请重试')
      })
      .finally(() => {
        if (!cancelled) setValuationLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [activeTab, valuationData])

  const handleGranularityChange = (g: Granularity) => {
    setHeatmapLoading(true)
    setGranularity(g)
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

  const handleValuationRetry = () => {
    setValuationData(null)
    setValuationError('')
  }

  const TAB_LABELS: Record<ActiveTab, string> = {
    heatmap: '资金流热力图',
    deviation: '错杀分析',
    valuation: '估值热度',
  }

  return (
    <DashboardShell>
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
        {(['heatmap', 'deviation', 'valuation'] as const).map((tab) => (
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
            {TAB_LABELS[tab]}
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
            将每只 ETF 近期在恐慌（FG&lt;45）或贪婪（FG&gt;55）期间的资金流强度与其自身历史基准对比，
            发现被市场过度抛售（错杀）或过度追高的行业。
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

          {deviationData && <ETFDeviationTable data={deviationData} />}
        </>
      )}

      {/* 估值热度 Tab */}
      {activeTab === 'valuation' && (
        <>
          <p className="text-sm text-gray-500 mb-4">
            基于 S&P 500 GICS 行业过去 10 年季度 PE 数据，计算当前估值 z-score，
            识别各行业的历史高估/低估程度。
          </p>

          {valuationError && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center justify-between">
              <span className="text-sm text-red-600">{valuationError}</span>
              <button
                onClick={handleValuationRetry}
                className="text-sm text-red-600 font-medium hover:text-red-800 underline"
              >
                重试
              </button>
            </div>
          )}

          {valuationLoading && !valuationData && (
            <div className="rounded-xl border border-gray-200 bg-white flex items-center justify-center h-64">
              <Spinner size={40} />
            </div>
          )}

          {valuationData && <SectorValuationGrid data={valuationData} />}
        </>
      )}
    </DashboardShell>
  )
}
