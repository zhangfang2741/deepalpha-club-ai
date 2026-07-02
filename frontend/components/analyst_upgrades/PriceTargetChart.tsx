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
import type { PriceTargetPoint } from '@/lib/api/analyst_upgrade'

interface TooltipState {
  visible: boolean
  x: number
  y: number
  label: string
  value: number
  count: number
}

// 月份标签 "2024-06" → "2024年6月"
export function formatMonthLabel(label: string): string {
  const [y, m] = label.split('-')
  if (!y || !m) return label
  return `${y}年${parseInt(m)}月`
}

interface PriceTargetChartProps {
  points: PriceTargetPoint[]
  synthetic?: boolean
}

/** 分析师平均目标价月度走势折线图（复用于弹窗与自定义查询） */
export default function PriceTargetChart({ points, synthetic = false }: PriceTargetChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const pointsByTime = useRef<Record<number, PriceTargetPoint>>({})
  const [tooltip, setTooltip] = useState<TooltipState>({
    visible: false, x: 0, y: 0, label: '', value: 0, count: 0,
  })

  useEffect(() => {
    if (!containerRef.current || points.length === 0) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#374151',
        fontSize: 12,
      },
      grid: {
        vertLines: { color: '#f3f4f6' },
        horzLines: { color: '#f3f4f6' },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, timeVisible: false },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: { labelVisible: false },
        horzLine: { labelVisible: true },
      },
      width: containerRef.current.clientWidth,
      height: 320,
    })

    const series = chart.addSeries(LineSeries, {
      color: '#3b82f6',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 5,
      crosshairMarkerBorderColor: '#3b82f6',
      crosshairMarkerBackgroundColor: '#fff',
    })

    // 月份标签 "2024-06" → unix 时间戳
    pointsByTime.current = {}
    const data = points.map((p) => {
      const [yearStr, monthStr] = p.label.split('-')
      const ts = Math.floor(new Date(parseInt(yearStr), parseInt(monthStr) - 1, 1).getTime() / 1000)
      pointsByTime.current[ts] = p
      return { time: ts as number, value: p.avg_target }
    })

    series.setData(data as never[])
    chart.timeScale().fitContent()

    chart.subscribeCrosshairMove((param) => {
      if (!param.point || !containerRef.current) {
        setTooltip((t) => ({ ...t, visible: false }))
        return
      }
      const price = param.seriesData.get(series)
      if (!price) {
        setTooltip((t) => ({ ...t, visible: false }))
        return
      }
      const ts = param.time as number
      const p = pointsByTime.current[ts]
      setTooltip({
        visible: true,
        x: param.point.x,
        y: param.point.y,
        label: p ? formatMonthLabel(p.label) : '',
        value: (price as { value: number }).value,
        count: p?.count ?? 0,
      })
    })

    chartRef.current = chart
    seriesRef.current = series

    const obs = new ResizeObserver(() => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth })
      }
    })
    obs.observe(containerRef.current)

    return () => {
      obs.disconnect()
      chart.remove()
      chartRef.current = null
    }
  }, [points])

  if (points.length === 0) {
    return (
      <div className="flex items-center justify-center h-60 text-gray-400 text-sm">
        暂无历史数据
      </div>
    )
  }

  const first = points[0]
  const last = points[points.length - 1]
  const totalPct = first.avg_target > 0
    ? ((last.avg_target - first.avg_target) / first.avg_target * 100).toFixed(1)
    : null

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-4 text-sm items-center">
        <span className="text-gray-500">起点 <span className="font-semibold text-gray-800">${first.avg_target.toFixed(0)}</span> <span className="text-xs text-gray-400">({formatMonthLabel(first.label)})</span></span>
        <span className="text-gray-500">最新 <span className="font-semibold text-gray-800">${last.avg_target.toFixed(0)}</span> <span className="text-xs text-gray-400">({formatMonthLabel(last.label)})</span></span>
        {totalPct && (
          <span className={`font-semibold ${parseFloat(totalPct) > 0 ? 'text-green-600' : 'text-red-500'}`}>
            区间涨幅 {parseFloat(totalPct) > 0 ? '+' : ''}{totalPct}%
          </span>
        )}
        {synthetic && (
          <span className="text-xs text-gray-400 ml-auto">数据基于近期聚合快照</span>
        )}
      </div>

      <div className="relative">
        <div ref={containerRef} className="w-full" />
        {tooltip.visible && (
          <div
            className="absolute pointer-events-none z-10 bg-gray-900 text-white text-xs rounded-lg px-3 py-2 shadow-lg"
            style={{
              left: tooltip.x + 12,
              top: tooltip.y - 10,
              transform: tooltip.x > 300 ? 'translateX(-110%)' : undefined,
            }}
          >
            <div className="font-semibold">{tooltip.label}</div>
            <div>均值目标价 <span className="text-blue-300">${tooltip.value.toFixed(2)}</span></div>
            {tooltip.count > 0 && (
              <div className="text-gray-400">{tooltip.count} 份报告</div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
