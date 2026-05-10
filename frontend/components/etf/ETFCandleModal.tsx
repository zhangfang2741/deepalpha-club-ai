'use client'

import { useEffect, useRef } from 'react'
import { createChart, ColorType, CandlestickSeries } from 'lightweight-charts'
import { fetchETFCandles } from '@/lib/api/etf'
import type { Granularity } from '@/lib/api/etf'

interface Props {
  symbol: string
  name: string
  granularity: Granularity
  onClose: () => void
}

export default function ETFCandleModal({ symbol, name, granularity, onClose }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 300,
      layout: { background: { type: ColorType.Solid, color: '#ffffff' }, textColor: '#374151' },
      grid: { vertLines: { color: 'rgba(156,163,175,0.15)' }, horzLines: { color: 'rgba(156,163,175,0.15)' } },
      timeScale: { timeVisible: false },
    })
    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#16a34a', downColor: '#ef4444',
      borderUpColor: '#16a34a', borderDownColor: '#ef4444',
      wickUpColor: '#16a34a', wickDownColor: '#ef4444',
    })

    fetchETFCandles(symbol, granularity).then((resp) => {
      const data = resp.candles.map((c) => ({
        time: c.t as `${number}-${number}-${number}`,
        open: c.o, high: c.h, low: c.l, close: c.c,
      }))
      series.setData(data)
      chart.timeScale().fitContent()
    })

    return () => chart.remove()
  }, [symbol, granularity])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-2xl mx-4 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div>
            <span className="font-bold text-gray-900 text-lg">{symbol}</span>
            <span className="ml-2 text-gray-500 text-sm">{name}</span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 text-xl font-bold">✕</button>
        </div>
        <div ref={containerRef} />
      </div>
    </div>
  )
}
