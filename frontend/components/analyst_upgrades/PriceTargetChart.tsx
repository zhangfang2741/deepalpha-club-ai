'use client'

import { useEffect, useRef } from 'react'
import {
  createChart,
  ColorType,
  LineSeries,
  IChartApi,
  ISeriesApi,
} from 'lightweight-charts'
import type { PriceTargetQuarter } from '@/lib/api/analyst_upgrade'

interface Props {
  symbol: string
  quarters: PriceTargetQuarter[]
}

export default function PriceTargetChart({ symbol, quarters }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)

  useEffect(() => {
    if (!containerRef.current || quarters.length === 0) return

    chartRef.current = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#6b7280',
      },
      grid: {
        vertLines: { color: '#f3f4f6' },
        horzLines: { color: '#f3f4f6' },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: {
        borderVisible: false,
        tickMarkFormatter: (time: number) => {
          // time 是 unix 秒，转为季度标签
          return ''
        },
      },
      crosshair: { vertLine: { labelVisible: true }, horzLine: { labelVisible: true } },
      width: containerRef.current.clientWidth,
      height: 260,
    })

    seriesRef.current = chartRef.current.addSeries(LineSeries, {
      color: '#3b82f6',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: true,
    })

    // lightweight-charts 用 unix timestamp 作 x 轴
    // 将季度标签转为该季度首月 1 日的时间戳
    const data = quarters.map((q) => {
      const [yearStr, qStr] = q.label.split(' Q')
      const year = parseInt(yearStr)
      const qn = parseInt(qStr)
      const month = (qn - 1) * 3 + 1
      const ts = Math.floor(new Date(year, month - 1, 1).getTime() / 1000)
      return { time: ts as number, value: q.avg_target }
    })

    seriesRef.current.setData(data as never[])
    chartRef.current.timeScale().fitContent()

    const resizeObs = new ResizeObserver(() => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth })
      }
    })
    resizeObs.observe(containerRef.current)

    return () => {
      resizeObs.disconnect()
      chartRef.current?.remove()
      chartRef.current = null
    }
  }, [quarters])

  if (quarters.length === 0) {
    return (
      <div className="flex items-center justify-center h-40 text-gray-400 text-sm">
        暂无历史数据
      </div>
    )
  }

  const first = quarters[0]
  const last = quarters[quarters.length - 1]
  const totalChange = first.avg_target > 0
    ? ((last.avg_target - first.avg_target) / first.avg_target * 100).toFixed(1)
    : '—'

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <span className="text-sm text-gray-500">{first.label}</span>
          <span className="mx-2 text-gray-300">→</span>
          <span className="text-sm text-gray-500">{last.label}</span>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-gray-500">起点 <span className="font-semibold text-gray-700">${first.avg_target.toFixed(0)}</span></span>
          <span className="text-gray-500">最新 <span className="font-semibold text-gray-700">${last.avg_target.toFixed(0)}</span></span>
          <span className={`font-semibold ${parseFloat(totalChange) > 0 ? 'text-green-600' : 'text-red-500'}`}>
            {parseFloat(totalChange) > 0 ? '+' : ''}{totalChange}%
          </span>
        </div>
      </div>
      <div ref={containerRef} className="w-full" />
    </div>
  )
}
