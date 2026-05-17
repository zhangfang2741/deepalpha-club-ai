'use client'
import { useEffect, useRef, useState } from 'react'
import { useSkillsStore } from '@/lib/store/skills'
import { createChart, CrosshairMode, CandlestickSeries, LineSeries, type Time } from 'lightweight-charts'
import { fetchKline } from '@/lib/api/skills'
import type { KlineResponse } from '@/lib/api/skills'

export function DetailPage() {
  const { selectedSkillId, detailSkill, detailLoading, closeDetail } = useSkillsStore()
  const klineRef = useRef<HTMLDivElement>(null)
  const factorRef = useRef<HTMLDivElement>(null)
  const [klineData, setKlineData] = useState<KlineResponse | null>(null)
  const [klineLoading, setKlineLoading] = useState(false)

  // 加载 K 线数据
  useEffect(() => {
    if (!detailSkill) return
    setKlineData(null)
    setKlineLoading(true)
    fetchKline(detailSkill.default_symbol, detailSkill.default_start_date, detailSkill.default_end_date, 'daily' as any)
      .then(setKlineData)
      .catch(() => {})
      .finally(() => setKlineLoading(false))
  }, [detailSkill?.default_symbol])

  // 渲染图表
  useEffect(() => {
    if (!klineRef.current || !factorRef.current) return
    if (!detailSkill) return

    const snapshot = (detailSkill.snapshot || {}) as { factor?: Array<{ time: string; value: number }>; metrics?: Record<string, number> }

    // K 线图
    const klineChart = createChart(klineRef.current, {
      layout: { background: { color: '#ffffff' }, textColor: '#374151' },
      grid: { vertLines: { color: '#f3f4f6' }, horzLines: { color: '#f3f4f6' } },
      crosshair: { mode: CrosshairMode.Normal },
      width: klineRef.current.clientWidth,
      height: 280,
    })

    const klineSeries = klineChart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderUpColor: '#22c55e',
      borderDownColor: '#ef4444',
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    })

    if (klineData?.klines?.length) {
      klineSeries.setData(klineData.klines.map((k) => ({
        time: k.time as Time,
        open: k.open,
        high: k.high,
        low: k.low,
        close: k.close,
      })))
    }
    klineChart.timeScale().fitContent()

    // 因子图
    const factorChart = createChart(factorRef.current, {
      layout: { background: { color: '#ffffff' }, textColor: '#374151' },
      grid: { vertLines: { color: '#f3f4f6' }, horzLines: { color: '#f3f4f6' } },
      crosshair: { mode: CrosshairMode.Normal },
      width: factorRef.current.clientWidth,
      height: 180,
    })

    const factorSeries = factorChart.addSeries(LineSeries, {
      color: '#3b82f6',
      lineWidth: 2,
    })

    const factorData = (snapshot.factor || [])
    factorSeries.setData(factorData.map((f) => ({ time: f.time as Time, value: f.value })))
    factorChart.timeScale().fitContent()

    const resizeObserver = new ResizeObserver(() => {
      if (klineRef.current) klineChart.applyOptions({ width: klineRef.current.clientWidth })
      if (factorRef.current) factorChart.applyOptions({ width: factorRef.current.clientWidth })
    })
    if (klineRef.current) resizeObserver.observe(klineRef.current)
    if (factorRef.current) resizeObserver.observe(factorRef.current)

    return () => {
      klineChart.remove()
      factorChart.remove()
      resizeObserver.disconnect()
    }
  }, [detailSkill, klineData])

  if (detailLoading) {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
        <div className="bg-white rounded-2xl p-8 text-center">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-gray-500">加载中...</p>
        </div>
      </div>
    )
  }

  if (!detailSkill) return null

  const metrics = ((detailSkill.snapshot || {}) as any)?.metrics || {}
  const narrative = (detailSkill.narrative as any) || {}

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-5xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-start justify-between p-6 border-b border-gray-100">
          <div>
            <div className="flex items-center gap-2 mb-1">
              {detailSkill.pin_priority === 1 && (
                <span className="text-xs font-semibold text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full">⭐ 精选</span>
              )}
              <span className="text-xs text-gray-400 font-mono">{detailSkill.default_symbol}</span>
            </div>
            <h2 className="text-xl font-bold text-gray-900">{detailSkill.title}</h2>
            <p className="text-sm text-gray-500 mt-1">{detailSkill.description}</p>
          </div>
          <button onClick={closeDetail} className="text-gray-400 hover:text-gray-600 text-2xl leading-none">×</button>
        </div>

        {/* 图表区域 */}
        <div className="p-6 space-y-4">
          {klineLoading ? (
            <div className="flex items-center justify-center h-64 bg-gray-50 rounded-xl">
              <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <>
              <div className="text-sm font-semibold text-gray-500 uppercase tracking-wide">K 线</div>
              <div ref={klineRef} className="w-full rounded-xl overflow-hidden" style={{ height: 280 }} />
            </>
          )}

          <div className="text-sm font-semibold text-gray-500 uppercase tracking-wide">因子</div>
          <div ref={factorRef} className="w-full rounded-xl overflow-hidden" style={{ height: 180 }} />

          {/* 指标卡 */}
          {Object.keys(metrics).length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricCard label="当前 Z" value={metrics.current_z} color="blue" />
              <MetricCard label="峰值 Z" value={metrics.peak_z} color="orange" />
              <MetricCard label="触发次数" value={metrics.trigger_count} color="green" />
              <MetricCard label="数据天数" value={metrics.data_days} color="purple" />
            </div>
          )}

          {/* AI 旁白 */}
          {narrative?.thesis && (
            <div className="bg-gray-50 rounded-xl p-5">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center text-white text-sm font-bold">α</div>
                <div>
                  <div className="text-sm font-semibold text-gray-700">DeepAlpha AI · 量化视角</div>
                </div>
              </div>
              <p className="text-sm text-gray-700 leading-relaxed">{narrative.thesis}</p>
            </div>
          )}

          {/* 底部操作 */}
          <div className="flex gap-3 pt-2">
            <button className="flex-1 py-2.5 rounded-lg border border-gray-300 text-gray-700 text-sm hover:bg-gray-50 transition-colors">
              换股重跑
            </button>
            <button className="flex-1 py-2.5 rounded-lg text-white text-sm bg-blue-600 hover:bg-blue-700 transition-colors shadow-md">
              保存到我的因子
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function MetricCard({ label, value, color }: { label: string; value?: number; color: 'blue' | 'orange' | 'green' | 'purple' }) {
  const colorMap = { blue: 'border-blue-500', orange: 'border-orange-500', green: 'border-green-500', purple: 'border-purple-500' }
  return (
    <div className={`bg-white border-l-4 ${colorMap[color]} rounded-lg p-4 shadow-sm`}>
      <div className="text-xs text-gray-400">{label}</div>
      <div className="text-lg font-bold text-gray-900 mt-0.5">{typeof value === 'number' ? value.toFixed(2) : '—'}</div>
    </div>
  )
}