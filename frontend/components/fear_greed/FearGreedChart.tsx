'use client'

import { useEffect, useRef, useState } from 'react'
import {
  createChart,
  ColorType,
  LineSeries,
  CrosshairMode,
  IChartApi,
  ISeriesApi,
} from 'lightweight-charts'
import { FearGreedPoint, FearGreedSnapshot } from '@/lib/api/fear_greed'

interface Props {
  history: FearGreedPoint[]
  current: FearGreedSnapshot
}

const RATING_COLOR: Record<string, string> = {
  'Extreme Greed': '#16a34a',
  'Greed': '#4ade80',
  'Neutral': '#ca8a04',
  'Fear': '#f87171',
  'Extreme Fear': '#ef4444',
}

const RATING_LABEL: Record<string, string> = {
  'Extreme Greed': '极度贪婪',
  'Greed': '贪婪',
  'Neutral': '中性',
  'Fear': '恐惧',
  'Extreme Fear': '极度恐惧',
}

function getColor(rating: string): string {
  return RATING_COLOR[rating] ?? '#3b82f6'
}

export default function FearGreedChart({ history, current }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const ratingByDateRef = useRef<Record<string, string>>({})
  const [tooltip, setTooltip] = useState<{
    visible: boolean
    x: number
    y: number
    date: string
    score: number
    rating: string
  }>({ visible: false, x: 0, y: 0, date: '', score: 0, rating: '' })

  // Effect 1: 仅在 mount/unmount 时创建/销毁图表
  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 340,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#374151',
      },
      grid: {
        vertLines: { color: 'rgba(156,163,175,0.15)' },
        horzLines: { color: 'rgba(156,163,175,0.15)' },
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
      color: getColor('Neutral'),
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 5,
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

    const chartData = history.map((p) => ({
      time: p.date as `${number}-${number}-${number}`,
      value: p.score,
    }))
    seriesRef.current.setData(chartData)
    seriesRef.current.applyOptions({ color: getColor(current.rating) })

    if (chartData.length > 0) {
      chartRef.current.timeScale().fitContent()
    }
  }, [history, current.rating])

  const currentColor = getColor(current.rating)

  return (
    <div className="relative">
      {/* 情绪色带背景（Y 轴锁定 0-100，色带按分值比例定位） */}
      <div
        className="absolute inset-0 pointer-events-none rounded-lg overflow-hidden"
        aria-hidden="true"
      >
        <div
          className="w-full h-full"
          style={{
            background: [
              'linear-gradient(to bottom,',
              'rgba(22,163,74,0.08) 0%,',
              'rgba(22,163,74,0.08) 24%,',
              'rgba(74,222,128,0.08) 24%,',
              'rgba(74,222,128,0.08) 44%,',
              'rgba(202,138,4,0.08) 44%,',
              'rgba(202,138,4,0.08) 55%,',
              'rgba(248,113,113,0.08) 55%,',
              'rgba(248,113,113,0.08) 75%,',
              'rgba(239,68,68,0.10) 75%,',
              'rgba(239,68,68,0.10) 100%)',
            ].join(' '),
          }}
        />
      </div>

      <div ref={containerRef} className="relative" style={{ height: 340 }} />

      {/* 当前值叠加显示 */}
      <div className="absolute top-3 left-4 pointer-events-none">
        <div className="text-4xl font-bold" style={{ color: currentColor }}>
          {Math.round(current.score)}
        </div>
        <div className="text-sm font-medium mt-0.5" style={{ color: currentColor }}>
          {RATING_LABEL[current.rating] ?? current.rating}
        </div>
      </div>

      {/* Crosshair Tooltip */}
      {tooltip.visible && (
        <div
          className="absolute pointer-events-none bg-white border border-gray-200 rounded-lg shadow-lg px-3 py-2 text-xs z-10"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          <div className="text-gray-500 mb-1">{tooltip.date}</div>
          <div className="font-bold text-base" style={{ color: getColor(tooltip.rating) }}>
            {Math.round(tooltip.score)}
          </div>
          <div className="font-medium" style={{ color: getColor(tooltip.rating) }}>
            {RATING_LABEL[tooltip.rating] ?? tooltip.rating}
          </div>
        </div>
      )}
    </div>
  )
}
