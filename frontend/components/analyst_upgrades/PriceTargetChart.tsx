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
import type { PriceTargetPoint, StockPricePoint } from '@/lib/api/analyst_upgrade'

const TARGET_COLOR = '#3b82f6'
const PRICE_COLOR = '#f59e0b'

interface TooltipState {
  visible: boolean
  x: number
  y: number
  label: string
  target: number | null
  count: number
  price: number | null
}

// 月份标签 "2024-06" → "2024年6月"
export function formatMonthLabel(label: string): string {
  const [y, m] = label.split('-')
  if (!y || !m) return label
  return `${y}年${parseInt(m)}月`
}

// 月份标签 "2024-06" → 该月 1 号的 unix 时间戳
function labelToTs(label: string): number {
  const [yearStr, monthStr] = label.split('-')
  return Math.floor(new Date(parseInt(yearStr), parseInt(monthStr) - 1, 1).getTime() / 1000)
}

interface PriceTargetChartProps {
  points: PriceTargetPoint[]
  pricePoints?: StockPricePoint[]
  synthetic?: boolean
}

/** 分析师平均目标价月度走势折线图，可叠加实际股价（复用于弹窗与自定义查询） */
export default function PriceTargetChart({ points, pricePoints = [], synthetic = false }: PriceTargetChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const targetSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const priceSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const targetByTime = useRef<Record<number, PriceTargetPoint>>({})
  const priceByTime = useRef<Record<number, number>>({})
  const [tooltip, setTooltip] = useState<TooltipState>({
    visible: false, x: 0, y: 0, label: '', target: null, count: 0, price: null,
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

    // 目标价折线
    const targetSeries = chart.addSeries(LineSeries, {
      color: TARGET_COLOR,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 5,
      crosshairMarkerBorderColor: TARGET_COLOR,
      crosshairMarkerBackgroundColor: '#fff',
    })

    targetByTime.current = {}
    const targetData = points.map((p) => {
      const ts = labelToTs(p.label)
      targetByTime.current[ts] = p
      return { time: ts as number, value: p.avg_target }
    })
    targetSeries.setData(targetData as never[])

    // 股价折线（可选）
    let priceSeries: ISeriesApi<'Line'> | null = null
    priceByTime.current = {}
    if (pricePoints.length > 0) {
      priceSeries = chart.addSeries(LineSeries, {
        color: PRICE_COLOR,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
        crosshairMarkerVisible: true,
        crosshairMarkerRadius: 5,
        crosshairMarkerBorderColor: PRICE_COLOR,
        crosshairMarkerBackgroundColor: '#fff',
      })
      const priceData = pricePoints.map((p) => {
        const ts = labelToTs(p.label)
        priceByTime.current[ts] = p.close
        return { time: ts as number, value: p.close }
      })
      priceSeries.setData(priceData as never[])
    }

    chart.timeScale().fitContent()

    chart.subscribeCrosshairMove((param) => {
      if (!param.point || !containerRef.current) {
        setTooltip((t) => ({ ...t, visible: false }))
        return
      }
      const ts = param.time as number
      const tp = targetByTime.current[ts]
      const priceVal = priceByTime.current[ts]
      if (tp === undefined && priceVal === undefined) {
        setTooltip((t) => ({ ...t, visible: false }))
        return
      }
      setTooltip({
        visible: true,
        x: param.point.x,
        y: param.point.y,
        label: tp ? formatMonthLabel(tp.label) : formatMonthLabel(labelFromTs(ts, pricePoints)),
        target: tp ? tp.avg_target : null,
        count: tp?.count ?? 0,
        price: priceVal ?? null,
      })
    })

    chartRef.current = chart
    targetSeriesRef.current = targetSeries
    priceSeriesRef.current = priceSeries

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
  }, [points, pricePoints])

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
        <span className="flex items-center gap-1.5 text-gray-500">
          <span className="inline-block w-3 h-0.5" style={{ backgroundColor: TARGET_COLOR }} />
          目标价
        </span>
        {pricePoints.length > 0 && (
          <span className="flex items-center gap-1.5 text-gray-500">
            <span className="inline-block w-3 h-0.5" style={{ backgroundColor: PRICE_COLOR }} />
            股价
          </span>
        )}
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
            {tooltip.target !== null && (
              <div>目标价 <span style={{ color: '#93c5fd' }}>${tooltip.target.toFixed(2)}</span></div>
            )}
            {tooltip.price !== null && (
              <div>股价 <span style={{ color: '#fcd34d' }}>${tooltip.price.toFixed(2)}</span></div>
            )}
            {tooltip.count > 0 && (
              <div className="text-gray-400">{tooltip.count} 份报告</div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// 当某个时间戳只有股价点时，从 pricePoints 反查其月份标签
function labelFromTs(ts: number, pricePoints: StockPricePoint[]): string {
  for (const p of pricePoints) {
    if (labelToTs(p.label) === ts) return p.label
  }
  return ''
}
