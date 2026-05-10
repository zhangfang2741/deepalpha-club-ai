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
import { FearGreedPoint, FearGreedSnapshot } from '@/lib/api/fear_greed'
import { RATING_COLOR, getRatingColor, getRatingLabel } from '@/lib/constants/fearGreed'

interface Props {
  history: FearGreedPoint[]
  current: FearGreedSnapshot
  onRangeChange?: (startDate: string, endDate: string) => void
}

export default function FearGreedChart({ history, current, onRangeChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const ratingByDateRef = useRef<Record<string, string>>({})
  const onRangeChangeRef = useRef(onRangeChange)
  const [tooltip, setTooltip] = useState<{
    visible: boolean
    x: number
    y: number
    date: string
    score: number
    rating: string
  }>({ visible: false, x: 0, y: 0, date: '', score: 0, rating: '' })

  // Keep ref updated
  useEffect(() => {
    onRangeChangeRef.current = onRangeChange
  }, [onRangeChange])

  // Effect 1: 仅在 mount/unmount 时创建/销毁图表
  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 340,
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
      color: getRatingColor('Neutral'),
      lineWidth: 3,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 6,
      crosshairMarkerBorderColor: '#ffffff',
      crosshairMarkerBorderWidth: 2,
      lineType: 2, // CurveLine for smoother curves
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
      const score = (seriesData as { value: number }).value
      const rating = ratingByDateRef.current[dateStr] ?? ''
      const x = param.point.x
      const y = param.point.y
      const containerWidth = containerRef.current.clientWidth
      const tooltipWidth = 160
      const adjustedX = x + tooltipWidth > containerWidth ? x - tooltipWidth - 10 : x + 10
      const adjustedY = Math.max(0, y - 60)
      setTooltip({ visible: true, x: adjustedX, y: adjustedY, date: dateStr, score, rating })
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
  }, []) // 空依赖：仅 mount/unmount 时执行

  // Effect 2: 数据或颜色变化时更新 series（不重建图表）
  useEffect(() => {
    if (!seriesRef.current || !chartRef.current) return

    ratingByDateRef.current = Object.fromEntries(history.map((p) => [p.date, p.rating]))

    const seen = new Map<string, number>()
    history.forEach((p) => seen.set(p.date, p.score))
    const chartData: LineData[] = Array.from(seen.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, score]) => ({
        time: date as `${number}-${number}-${number}`,
        value: score,
      }))
    
    // 根据当前评分设置渐变色
    const currentColor = getRatingColor(current.rating)
    seriesRef.current.setData(chartData)
    seriesRef.current.applyOptions({
      color: currentColor,
      lineType: 2, // CurveLine
      lineWidth: 3,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 6,
      crosshairMarkerBorderColor: '#ffffff',
      crosshairMarkerBorderWidth: 2,
    })

    if (chartData.length > 0) {
      chartRef.current.timeScale().fitContent()
    }
  }, [history, current.rating])

  const currentColor = getRatingColor(current.rating)

  // @ts-ignore
    return (
    <div className="relative">
      {/* 情绪色带背景（Y 轴锁定 0-100，色带按分值比例定位） */}
      <div
        className="absolute inset-0 pointer-events-none rounded-xl overflow-hidden"
        aria-hidden="true"
      >
        <div
          className="w-full h-full opacity-60"
          style={{
            background: [
              'linear-gradient(to bottom,',
              'rgba(239,68,68,0.15) 0%,',
              'rgba(239,68,68,0.15) 24%,',
              'rgba(248,113,113,0.10) 24%,',
              'rgba(248,113,113,0.10) 44%,',
              'rgba(202,138,4,0.08) 44%,',
              'rgba(202,138,4,0.08) 55%,',
              'rgba(74,222,128,0.10) 55%,',
              'rgba(74,222,128,0.10) 75%,',
              'rgba(22,163,74,0.12) 75%,',
              'rgba(22,163,74,0.12) 100%)',
            ].join(' '),
          }}
        />
      </div>

      <div ref={containerRef} className="relative" style={{ height: 340 }} />

      {/* 当前值叠加显示 */}
      <div className="absolute top-4 left-5 pointer-events-none">
        <div 
          className="text-5xl font-bold tracking-tight drop-shadow-sm" 
          style={{ color: currentColor }}
        >
          {Math.round(current.score)}
        </div>
        <div 
          className="text-sm font-semibold mt-1 uppercase tracking-wide" 
          style={{ color: currentColor }}
        >
          {getRatingLabel(current.rating)}
        </div>
      </div>

      {/* Crosshair Tooltip */}
      {tooltip.visible && (
        <div
          className="absolute pointer-events-none bg-white/95 backdrop-blur-sm border border-gray-200/80 rounded-xl shadow-xl px-4 py-3 text-xs z-10 transition-all duration-150"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          <div className="text-gray-500 mb-1.5 font-medium">{tooltip.date}</div>
          <div className="font-bold text-2xl mb-0.5" style={{ color: getRatingColor(tooltip.rating) }}>
            {Math.round(tooltip.score)}
          </div>
          <div className="font-semibold uppercase tracking-wide" style={{ color: getRatingColor(tooltip.rating) }}>
            {getRatingLabel(tooltip.rating)}
          </div>
        </div>
      )}

      {/* 颜色区间图例 */}
      <div className="flex items-center justify-center gap-4 mt-3 text-xs">
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: RATING_COLOR['Extreme Greed'] }}></div>
          <span className="text-gray-600">极度贪婪</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: RATING_COLOR['Greed'] }}></div>
          <span className="text-gray-600">贪婪</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: RATING_COLOR['Neutral'] }}></div>
          <span className="text-gray-600">中性</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: RATING_COLOR['Fear'] }}></div>
          <span className="text-gray-600">恐惧</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: RATING_COLOR['Extreme Fear'] }}></div>
          <span className="text-gray-600">极度恐惧</span>
        </div>
      </div>
    </div>
  )
}
