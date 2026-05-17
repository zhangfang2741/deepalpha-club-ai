'use client'

import { useEffect, useState } from 'react'
import { fetchETFHeatmap } from '@/lib/api/etf'
import type { HeatmapResponse, Granularity } from '@/lib/api/etf'
import { useETFStore } from '@/lib/store/etf'
import GranularityToggle from '@/components/etf/GranularityToggle'
import ETFHeatmapTable from '@/components/etf/ETFHeatmapTable'
import SectorValuationGrid from '@/components/valuation/SectorValuationGrid'
import Spinner from '@/components/ui/Spinner'
import DashboardShell from '@/components/layout/DashboardShell'

type ActiveTab = 'heatmap' | 'valuation'

export default function ETFPage() {
  const { granularity, days, setGranularity } = useETFStore()
  const [activeTab, setActiveTab] = useState<ActiveTab>('heatmap')

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

  const TAB_LABELS: Record<ActiveTab, string> = {
    heatmap: '资金流热力图',
    valuation: '行业估值分析',
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
        {(['heatmap', 'valuation'] as const).map((tab) => (
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

      {/* 行业估值分析 Tab */}
      {activeTab === 'valuation' && (
        <>
          {/* 计算方法说明卡片 */}
          <div className="mb-4 p-4 bg-slate-50 border border-slate-200 rounded-xl text-sm">
            <div className="font-semibold text-slate-700 mb-3">计算方法（PE z-score）</div>
            <div className="space-y-2 text-slate-600">
              <div>
                <span className="font-medium text-slate-800">1. 数据采集</span>
                ：从 FMP 拉取 GICS 各行业近 5 年（约 20 个季度）的季度末市盈率（PE）历史序列。
              </div>
              <div>
                <span className="font-medium text-slate-800">2. 标准化公式</span>
                ：
                <code className="mx-1.5 px-2 py-0.5 bg-white border border-slate-200 rounded text-xs font-mono text-slate-700">
                  z-score = (当前 PE − 历史均值 μ) / 历史标准差 σ
                </code>
              </div>
              <div>
                <span className="font-medium text-slate-800">3. 热度分级</span>
                ：根据 z-score 落入的标准差区间判断估值冷热——
                <span className="text-blue-700 font-medium"> z ≤ −2σ</span> 极度低估 ·
                <span className="text-blue-500 font-medium"> −2σ ~ −1σ</span> 低估 ·
                <span className="text-slate-500 font-medium"> −1σ ~ +1σ</span> 中性 ·
                <span className="text-orange-500 font-medium"> +1σ ~ +2σ</span> 高估 ·
                <span className="text-red-500 font-medium"> z ≥ +2σ</span> 极度高估
              </div>
            </div>

            {/* 示例 */}
            <div className="mt-3 p-3 bg-white border border-slate-100 rounded-lg">
              <div className="text-xs font-semibold text-slate-600 mb-2">示例：信息技术行业</div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                <div className="space-y-0.5">
                  <div className="text-slate-400">历史均值 μ（5年）</div>
                  <div className="font-mono font-bold text-slate-700">28.00</div>
                </div>
                <div className="space-y-0.5">
                  <div className="text-slate-400">历史标准差 σ</div>
                  <div className="font-mono font-bold text-slate-700">4.20</div>
                </div>
                <div className="space-y-0.5">
                  <div className="text-slate-400">当前 PE</div>
                  <div className="font-mono font-bold text-slate-700">35.00</div>
                </div>
              </div>
              <div className="mt-2 text-xs text-slate-500 border-t border-slate-50 pt-2">
                z-score = (35.00 − 28.00) / 4.20 ≈{' '}
                <span className="font-bold font-mono text-orange-500">+1.67</span>
                <span className="ml-2">→ 落在 [+1σ, +2σ) 区间 →</span>
                <span className="ml-1 font-semibold text-orange-500">高估</span>
              </div>
            </div>
          </div>

          <SectorValuationGrid />
        </>
      )}
    </DashboardShell>
  )
}
