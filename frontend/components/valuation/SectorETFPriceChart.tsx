'use client'

import { useEffect, useRef } from 'react'
import {
  createChart,
  ColorType,
  LineSeries,
  CrosshairMode,
  IChartApi,
  ISeriesApi,
  LineData,
  AreaSeries,
} from 'lightweight-charts'
import type { ETFPricePoint } from '@/lib/api/valuation'

interface Props {
  symbol: string
  prices: ETFPricePoint[]
}

export default function SectorETFPriceChart({ symbol, prices }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Area'> | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 220,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#64748b',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: 'rgba(148,163,184,0.08)' },
        horzLines: { color: 'rgba(148,163,184,0.10)' },
      },
      crosshair: { mode: CrosshairMode.Magnet },
      rightPriceScale: { borderColor: 'rgba(148,163,184,0.3)' },
      timeScale: {
        borderColor: 'rgba(148,163,184,0.3)',
        timeVisible: false,
        secondsVisible: false,
      },
    })

    const series = chart.addSeries(AreaSeries, {
      lineColor: '#0ea5e9',
      topColor: 'rgba(14,165,233,0.30)',
      bottomColor: 'rgba(14,165,233,0.02)',
      lineWidth: 2,
      priceLineVisible: true,
      lastValueVisible: true,
    })

    chartRef.current = chart
    seriesRef.current = series

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!seriesRef.current || !chartRef.current) return
    const data: LineData[] = prices.map((p) => ({ time: p.date, value: p.close }))
    seriesRef.current.setData(data)
    chartRef.current.timeScale().fitContent()
  }, [prices])

  const first = prices[0]
  const last = prices[prices.length - 1]
  const changePct = first && last ? ((last.close - first.close) / first.close) * 100 : null
  const changeColor = changePct === null ? '#94a3b8' : changePct >= 0 ? '#16a34a' : '#dc2626'

  return (
    <div className="w-full">
      <div className="flex items-baseline justify-between px-1 pb-2">
        <div className="flex items-baseline gap-3">
          <span className="text-sm font-bold text-slate-900 font-mono">{symbol}</span>
          {last && (
            <span className="text-2xl font-bold text-slate-900 font-mono">${last.close.toFixed(2)}</span>
          )}
          {changePct !== null && (
            <span className="text-xs font-bold font-mono" style={{ color: changeColor }}>
              {changePct >= 0 ? '+' : ''}
              {changePct.toFixed(2)}%
              <span className="text-slate-400 ml-1 font-normal">{prices.length}日</span>
            </span>
          )}
        </div>
        {first && last && (
          <span className="text-xs text-slate-400 font-mono">
            {first.date} — {last.date}
          </span>
        )}
      </div>
      <div ref={containerRef} className="w-full" />
    </div>
  )
}
