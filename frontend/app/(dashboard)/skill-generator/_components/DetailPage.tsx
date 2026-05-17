'use client'
import { useEffect, useRef } from 'react'
import { useSkillsStore } from '@/lib/store/skills'

export function DetailPage() {
  const { selectedSkillId, detailSkill, detailLoading, closeDetail } = useSkillsStore()
  const klineRef = useRef<HTMLDivElement>(null)
  const factorRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!detailSkill?.snapshot || !klineRef.current || !factorRef.current) return

    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { createChart, ColorType, BaselineSeries, CrosshairMode } = require('lightweight-charts') as typeof import('lightweight-charts')
    const snapshot = detailSkill.snapshot as { factor?: Array<{ time: string; value: number }>; signals?: Array<{ date: string; z: number; close: number }>; metrics?: Record<string, number> }
    const signals = snapshot.signals || []

    // K 线图
    const klineChart = createChart(klineRef.current, {
      layout: { background: { color: '#ffffff' }, textColor: '#374151' },
      grid: { vertLines: { color: '#f3f4f6' }, horzLines: { color: '#f3f4f6' } },
      crosshair: { mode: CrosshairMode.Normal },
      width: klineRef.current.clientWidth,
      height: 300,
    })

    // 简化 mock K 线（实际从 API 拉）
    const mockCandles = (snapshot.factor || []).slice(-100).map((f, i) => ({
      time: f.time as any,
      open: 100 + i * 0.5,
      high: 102 + i * 0.5,
      low: 99 + i * 0.5,
      close: 101 + i * 0.5,
    }))
    const klineSeries = klineChart.addCandlestickSeries({ upColor: '#22c55e', downColor: '#ef4444' })
    klineSeries.setData(mockCandles)
    klineChart.timeScale().fitContent()

    // 因子图
    const factorChart = createChart(factorRef.current, {
      layout: { background: { color: '#ffffff' }, textColor: '#374151' },
      grid: { vertLines: { color: '#f3f4f6' }, horzLines: { color: '#f3f4f6' } },
      crosshair: { mode: CrosshairMode.Normal },
      width: factorRef.current.clientWidth,
      height: 200,
    })
    const baselineSeries = factorChart.addSeries(BaselineSeries, {
      topFillColor1: '#3b82f6',
      topFillColor2: '#3b82f640',
      bottomFillColor1: '#ef4444',
      bottomFillColor2: '#ef444440',
      baseValue: { type: 'zero' },
    })
    baselineSeries.setData((snapshot.factor || []).map((f) => ({ time: f.time as any, value: f.value })))
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
  }, [detailSkill])

  if (detailLoading) {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
        <div className="bg-white rounded-2xl p-8 text-center">
          <div className="animate-spin text-3xl mb-4">⚙️</div>
          <p className="text-gray-500">加载中...</p>
        </div>
      </div>
    )
  }

  if (!detailSkill) return null

  const metrics = (detailSkill.snapshot as any)?.metrics || {}
  const narrative = (detailSkill.narrative as any) || {}

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-5xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-start justify-between p-6 border-b border-gray-100">
          <div>
            <div className="flex items-center gap-2 mb-1">
              {detailSkill.pin_priority === 1 && (
                <span className="text-xs font-semibold text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full">
                  ⭐ 精选
                </span>
              )}
              <span className="text-xs text-gray-400 font-mono">{detailSkill.default_symbol}</span>
            </div>
            <h2 className="text-xl font-bold text-gray-900">{detailSkill.title}</h2>
            <p className="text-sm text-gray-500 mt-1">{detailSkill.description}</p>
          </div>
          <button onClick={closeDetail} className="text-gray-400 hover:text-gray-600 text-2xl leading-none">×</button>
        </div>

        {/* 双图 */}
        <div className="p-6 space-y-4">
          <div className="text-sm font-semibold text-gray-500 uppercase tracking-wide">K 线</div>
          <div ref={klineRef} className="w-full rounded-xl overflow-hidden" style={{ height: 300 }} />

          <div className="text-sm font-semibold text-gray-500 uppercase tracking-wide">因子</div>
          <div ref={factorRef} className="w-full rounded-xl overflow-hidden" style={{ height: 200 }} />

          {/* 指标卡 */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard label="当前 Z" value={metrics.current_z} color="blue" />
            <MetricCard label="峰值 Z" value={metrics.peak_z} color="orange" />
            <MetricCard label="触发次数" value={metrics.trigger_count} color="green" />
            <MetricCard label="数据天数" value={metrics.data_days} color="purple" />
          </div>

          {/* AI 旁白 */}
          {narrative.thesis && (
            <div className="bg-gray-50 rounded-xl p-5">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center text-white text-sm font-bold">α</div>
                <div>
                  <div className="text-sm font-semibold text-gray-700">DeepAlpha AI · 资深量化研究员视角</div>
                </div>
              </div>
              <p className="text-sm text-gray-700 leading-relaxed">{narrative.thesis}</p>
              {narrative.key_points?.length > 0 && (
                <div className="mt-4 space-y-3">
                  {narrative.key_points.map((point: any, i: number) => (
                    <div key={i} className="flex gap-3">
                      <div className={`w-0.5 rounded-full shrink-0 ${i === 0 ? 'bg-blue-500 h-6' : i === 1 ? 'bg-orange-500 h-6' : 'bg-green-500 h-6'}`} />
                      <div>
                        <div className="text-xs text-gray-400">{point.date}  z={point.z}</div>
                        <div className="text-sm text-gray-600 mt-0.5">{point.text}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {narrative.verdict && (
                <div className="mt-4 flex gap-4 text-xs">
                  <span className="text-green-600">✓ {narrative.verdict.applicable}</span>
                  <span className="text-red-500">✗ {narrative.verdict.fails}</span>
                </div>
              )}
            </div>
          )}

          {/* 底部操作 */}
          <div className="flex gap-3 pt-2">
            <button className="flex-1 py-2.5 rounded-lg border border-gray-300 text-gray-700 text-sm hover:bg-gray-50 transition-colors">
              换股重跑
            </button>
            <button className="flex-1 py-2.5 rounded-lg text-white text-sm bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 transition-colors shadow-md">
              保存到我的因子
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function MetricCard({ label, value, color }: { label: string; value?: number; color: 'blue' | 'orange' | 'green' | 'purple' }) {
  const colorMap = {
    blue: 'border-blue-500',
    orange: 'border-orange-500',
    green: 'border-green-500',
    purple: 'border-purple-500',
  }
  return (
    <div className={`bg-white border-l-4 ${colorMap[color]} rounded-lg p-4 shadow-sm`}>
      <div className="text-xs text-gray-400">{label}</div>
      <div className="text-lg font-bold text-gray-900 mt-0.5">{typeof value === 'number' ? value.toFixed(2) : '—'}</div>
    </div>
  )
}