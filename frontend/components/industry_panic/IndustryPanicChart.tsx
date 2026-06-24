'use client'

import { useEffect, useRef, useState } from 'react'
import {
  createChart,
  ColorType,
  LineSeries,
  CrosshairMode,
  IChartApi,
  ISeriesApi,
  LineData,
} from 'lightweight-charts'
import type { SectorPanic } from '@/lib/api/industry_panic'
import { getRsiColor, getRsiLevel } from '@/lib/constants/industryPanic'

interface Props {
  sector: SectorPanic
}

export default function IndustryPanicChart({ sector }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const [tooltip, setTooltip] = useState<{
    visible: boolean
    x: number
    y: number
    date: string
    rsi: number
  }>({ visible: false, x: 0, y: 0, date: '', rsi: 0 })

  // 仅 mount/unmount 创建/销毁图表
  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 300,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#6b7280',
        fontSize: 12,
      },
      grid: {
        vertLines: { color: 'rgba(156,163,175,0.08)', style: 2 },
        horzLines: { color: 'rgba(156,163,175,0.08)', style: 2 },
      },
      crosshair: { mode: CrosshairMode.Magnet },
      rightPriceScale: { borderColor: 'rgba(156,163,175,0.3)' },
      timeScale: {
        borderColor: 'rgba(156,163,175,0.3)',
        timeVisible: false,
      },
    })
    chartRef.current = chart

    const lineSeries = chart.addSeries(LineSeries, {
      color: '#ca8a04',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 5,
      crosshairMarkerBorderColor: '#ffffff',
      crosshairMarkerBorderWidth: 2,
      lineType: 2,
    })
    seriesRef.current = lineSeries

    lineSeries.applyOptions({
      autoscaleInfoProvider: () => ({
        priceRange: { minValue: 0, maxValue: 100 },
        margins: { above: 2, below: 2 },
      }),
    })

    chart.subscribeCrosshairMove((param) => {
      if (!param.point || !param.time || !containerRef.current) {
        setTooltip((t) => ({ ...t, visible: false }))
        return
      }
      const seriesData = param.seriesData.get(lineSeries)
      if (!seriesData || !('value' in seriesData)) {
        setTooltip((t) => ({ ...t, visible: false }))
        return
      }
      const dateStr = String(param.time)
      const rsi = (seriesData as { value: number }).value
      const x = param.point.x
      const y = param.point.y
      const containerWidth = containerRef.current.clientWidth
      const tooltipWidth = 160
      const adjustedX = x + tooltipWidth > containerWidth ? x - tooltipWidth - 10 : x + 10
      const adjustedY = Math.max(0, y - 60)
      setTooltip({ visible: true, x: adjustedX, y: adjustedY, date: dateStr, rsi })
    })

    const observer = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    })
    observer.observe(containerRef.current)

    return () => {
      observer.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // 数据或行业切换时更新 series
  useEffect(() => {
    if (!seriesRef.current || !chartRef.current) return

    const chartData: LineData[] = sector.history.map((p) => ({
      time: p.date as `${number}-${number}-${number}`,
      value: p.rsi,
    }))

    const currentRsi = sector.current_rsi ?? 50
    const color = getRsiColor(currentRsi)

    seriesRef.current.setData(chartData)
    seriesRef.current.applyOptions({ color })

    if (chartData.length > 0) {
      chartRef.current.timeScale().fitContent()
    }
  }, [sector])

  const currentRsi = sector.current_rsi ?? 50
  const currentLevel = getRsiLevel(currentRsi)

  return (
    <div className="relative">
      {/*
        色带背景：Y 轴 0→100，图表从上到下对应 RSI 高→低
        顶部（RSI 70-100）= 超买 = 蓝
        中间（RSI 30-70） = 中性 = 淡黄
        底部（RSI 0-30）  = 超卖 = 红
      */}
      <div
        className="absolute inset-0 pointer-events-none rounded-xl overflow-hidden"
        aria-hidden="true"
      >
        <div
          className="w-full h-full opacity-50"
          style={{
            background: [
              'linear-gradient(to bottom,',
              'rgba(29,78,216,0.14) 0%,',
              'rgba(59,130,246,0.10) 30%,',
              'rgba(202,138,4,0.08) 30%,',
              'rgba(202,138,4,0.08) 70%,',
              'rgba(249,115,22,0.12) 70%,',
              'rgba(239,68,68,0.18) 100%)',
            ].join(' '),
          }}
        />
      </div>

      <div ref={containerRef} className="relative" style={{ height: 300 }} />

      {/* 当前 RSI 值浮层 */}
      <div className="absolute top-3 left-4 pointer-events-none">
        <div
          className="text-4xl font-bold tracking-tight drop-shadow-sm"
          style={{ color: currentLevel.color }}
        >
          {currentRsi.toFixed(1)}
        </div>
        <div
          className="text-xs font-bold mt-0.5 uppercase tracking-wide"
          style={{ color: currentLevel.color }}
        >
          {currentLevel.label}
        </div>
      </div>

      {/* Crosshair Tooltip */}
      {tooltip.visible && (
        <div
          className="absolute pointer-events-none bg-white/95 backdrop-blur-sm border border-gray-200/80 rounded-xl shadow-xl px-4 py-3 text-xs z-10"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          <div className="text-gray-500 mb-1.5 font-medium">{tooltip.date}</div>
          <div
            className="font-bold text-2xl mb-0.5"
            style={{ color: getRsiColor(tooltip.rsi) }}
          >
            {tooltip.rsi.toFixed(1)}
          </div>
          <div
            className="font-semibold uppercase tracking-wide text-[10px]"
            style={{ color: getRsiColor(tooltip.rsi) }}
          >
            {getRsiLevel(tooltip.rsi).label}
          </div>
        </div>
      )}

      {/* 图例 */}
      <div className="flex items-center justify-center gap-3 mt-3 flex-wrap text-xs">
        {([
          { label: '超卖 (<30)', color: '#ef4444' },
          { label: '偏弱 (30-45)', color: '#f97316' },
          { label: '中性 (45-55)', color: '#ca8a04' },
          { label: '偏强 (55-70)', color: '#3b82f6' },
          { label: '超买 (>70)', color: '#1d4ed8' },
        ] as const).map((item) => (
          <div key={item.label} className="flex items-center gap-1">
            <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: item.color }} />
            <span className="text-gray-600">{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
