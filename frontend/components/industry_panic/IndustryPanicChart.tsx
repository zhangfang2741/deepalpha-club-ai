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
import type { SectorWithIndustries } from '@/lib/api/valuation'
import { zScoreToPanic, getPanicColor, getPanicLevel } from '@/lib/constants/industryPanic'

interface Props {
  sector: SectorWithIndustries
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
    panic: number
    pe: number
  }>({ visible: false, x: 0, y: 0, date: '', panic: 0, pe: 0 })

  // 只在 mount/unmount 创建/销毁图表
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
      const panic = (seriesData as { value: number }).value
      const peRecord = sector.hist_pe.find((p) => p.date === dateStr)
      const pe = peRecord?.pe ?? 0
      const x = param.point.x
      const y = param.point.y
      const containerWidth = containerRef.current.clientWidth
      const tooltipWidth = 160
      const adjustedX = x + tooltipWidth > containerWidth ? x - tooltipWidth - 10 : x + 10
      const adjustedY = Math.max(0, y - 60)
      setTooltip({ visible: true, x: adjustedX, y: adjustedY, date: dateStr, panic, pe })
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

  // 数据更新时重设 series
  useEffect(() => {
    if (!seriesRef.current || !chartRef.current) return
    if (!sector.hist_mean || !sector.hist_std || sector.hist_std === 0) return

    const { hist_mean, hist_std, hist_pe } = sector

    const chartData: LineData[] = hist_pe
      .filter((p) => p.pe != null)
      .sort((a, b) => a.date.localeCompare(b.date))
      .map((p) => {
        const z = (p.pe - hist_mean) / hist_std
        const panic = zScoreToPanic(z)
        return {
          time: p.date as `${number}-${number}-${number}`,
          value: panic,
        }
      })

    const currentPanic = zScoreToPanic(sector.z_score)
    const color = getPanicColor(currentPanic)

    seriesRef.current.setData(chartData)
    seriesRef.current.applyOptions({ color })

    if (chartData.length > 0) {
      chartRef.current.timeScale().fitContent()
    }
  }, [sector])

  const currentPanic = zScoreToPanic(sector.z_score)
  const currentLevel = getPanicLevel(currentPanic)

  return (
    <div className="relative">
      {/* 情绪色带背景 */}
      <div
        className="absolute inset-0 pointer-events-none rounded-xl overflow-hidden"
        aria-hidden="true"
      >
        <div
          className="w-full h-full opacity-50"
          style={{
            background: [
              'linear-gradient(to bottom,',
              'rgba(239,68,68,0.18) 0%,',
              'rgba(239,68,68,0.18) 20%,',
              'rgba(249,115,22,0.12) 20%,',
              'rgba(249,115,22,0.12) 40%,',
              'rgba(202,138,4,0.08) 40%,',
              'rgba(202,138,4,0.08) 60%,',
              'rgba(59,130,246,0.10) 60%,',
              'rgba(59,130,246,0.10) 80%,',
              'rgba(29,78,216,0.14) 80%,',
              'rgba(29,78,216,0.14) 100%)',
            ].join(' '),
          }}
        />
      </div>

      <div ref={containerRef} className="relative" style={{ height: 300 }} />

      {/* 当前恐慌值浮层 */}
      <div className="absolute top-3 left-4 pointer-events-none">
        <div
          className="text-4xl font-bold tracking-tight drop-shadow-sm"
          style={{ color: currentLevel.color }}
        >
          {Math.round(currentPanic)}
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
            style={{ color: getPanicColor(tooltip.panic) }}
          >
            {Math.round(tooltip.panic)}
          </div>
          <div
            className="font-semibold uppercase tracking-wide text-[10px]"
            style={{ color: getPanicColor(tooltip.panic) }}
          >
            {getPanicLevel(tooltip.panic).label}
          </div>
          {tooltip.pe > 0 && (
            <div className="text-gray-400 mt-1.5 font-mono">PE {tooltip.pe.toFixed(2)}</div>
          )}
        </div>
      )}

      {/* 图例 */}
      <div className="flex items-center justify-center gap-3 mt-3 flex-wrap text-xs">
        {([
          { label: '极度恐慌', color: '#ef4444' },
          { label: '恐慌', color: '#f97316' },
          { label: '中性', color: '#ca8a04' },
          { label: '平静', color: '#3b82f6' },
          { label: '极度平静', color: '#1d4ed8' },
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
