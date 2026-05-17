'use client'
import { useEffect, useRef } from 'react'
import {
  createChart, CrosshairMode, CandlestickSeries, LineSeries, HistogramSeries,
  type IChartApi, type ISeriesApi, type Time,
} from 'lightweight-charts'
import type { KlineBar, FactorPoint } from '@/lib/api/skills'

interface Props {
  klines: KlineBar[]
  factor: FactorPoint[]
  klineLoading?: boolean
  factorLoading?: boolean
  emptyHint?: string
}

// 简单移动平均线（period 之前的点输出 null，前端过滤）
function sma(closes: number[], period: number): (number | null)[] {
  const out: (number | null)[] = []
  let sum = 0
  for (let i = 0; i < closes.length; i++) {
    sum += closes[i]
    if (i >= period) sum -= closes[i - period]
    out.push(i >= period - 1 ? sum / period : null)
  }
  return out
}

const MA_CONFIGS: Array<{ period: number; color: string }> = [
  { period: 5, color: '#f59e0b' },
  { period: 10, color: '#a855f7' },
  { period: 20, color: '#ec4899' },
]

export function KlineFactorChart({ klines, factor, klineLoading, factorLoading, emptyHint }: Props) {
  const klineRef = useRef<HTMLDivElement>(null)
  const factorRef = useRef<HTMLDivElement>(null)
  const klineChartRef = useRef<IChartApi | null>(null)
  const factorChartRef = useRef<IChartApi | null>(null)
  const klineSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const maSeriesRefs = useRef<ISeriesApi<'Line'>[]>([])
  const factorSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)

  // 初始化图表（仅一次）
  useEffect(() => {
    if (!klineRef.current || !factorRef.current) return

    const klineChart = createChart(klineRef.current, {
      layout: { background: { color: '#ffffff' }, textColor: '#374151' },
      grid: { vertLines: { color: '#f3f4f6' }, horzLines: { color: '#f3f4f6' } },
      crosshair: { mode: CrosshairMode.Normal },
      width: klineRef.current.clientWidth,
      height: klineRef.current.clientHeight,
      timeScale: { rightOffset: 4, barSpacing: 6 },
      rightPriceScale: { scaleMargins: { top: 0.05, bottom: 0.28 } },
    })

    // 蜡烛
    const klineSeries = klineChart.addSeries(CandlestickSeries, {
      upColor: '#22c55e', downColor: '#ef4444',
      borderUpColor: '#22c55e', borderDownColor: '#ef4444',
      wickUpColor: '#22c55e', wickDownColor: '#ef4444',
    })

    // 均线（叠加在主图）
    const maSeries = MA_CONFIGS.map(({ color }) =>
      klineChart.addSeries(LineSeries, {
        color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
      }),
    )

    // 成交量（overlay 在主图底部 25%）
    const volumeSeries = klineChart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: '',
      color: '#9ca3af',
    })
    volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.75, bottom: 0 } })

    const factorChart = createChart(factorRef.current, {
      layout: { background: { color: '#ffffff' }, textColor: '#374151' },
      grid: { vertLines: { color: '#f3f4f6' }, horzLines: { color: '#f3f4f6' } },
      crosshair: { mode: CrosshairMode.Normal },
      width: factorRef.current.clientWidth,
      height: factorRef.current.clientHeight,
      timeScale: { rightOffset: 4, barSpacing: 6 },
    })
    const factorSeries = factorChart.addSeries(LineSeries, {
      color: '#3b82f6', lineWidth: 2,
    })

    klineChartRef.current = klineChart
    factorChartRef.current = factorChart
    klineSeriesRef.current = klineSeries
    volumeSeriesRef.current = volumeSeries
    maSeriesRefs.current = maSeries
    factorSeriesRef.current = factorSeries

    // 时间轴联动
    const syncFromKline = () => {
      const range = klineChart.timeScale().getVisibleLogicalRange()
      if (range) factorChart.timeScale().setVisibleLogicalRange(range)
    }
    const syncFromFactor = () => {
      const range = factorChart.timeScale().getVisibleLogicalRange()
      if (range) klineChart.timeScale().setVisibleLogicalRange(range)
    }
    klineChart.timeScale().subscribeVisibleLogicalRangeChange(syncFromKline)
    factorChart.timeScale().subscribeVisibleLogicalRangeChange(syncFromFactor)

    const ro = new ResizeObserver(() => {
      if (klineRef.current) klineChart.applyOptions({ width: klineRef.current.clientWidth, height: klineRef.current.clientHeight })
      if (factorRef.current) factorChart.applyOptions({ width: factorRef.current.clientWidth, height: factorRef.current.clientHeight })
    })
    if (klineRef.current) ro.observe(klineRef.current)
    if (factorRef.current) ro.observe(factorRef.current)

    return () => {
      ro.disconnect()
      klineChart.remove()
      factorChart.remove()
      klineChartRef.current = null
      factorChartRef.current = null
      klineSeriesRef.current = null
      volumeSeriesRef.current = null
      maSeriesRefs.current = []
      factorSeriesRef.current = null
    }
  }, [])

  // K 线 + 均线 + 成交量 数据更新（不调用 fitContent，由因子图同步时间轴）
  useEffect(() => {
    if (!klineSeriesRef.current || !volumeSeriesRef.current) return

    klineSeriesRef.current.setData(
      klines.map((k) => ({ time: k.time as Time, open: k.open, high: k.high, low: k.low, close: k.close })),
    )

    volumeSeriesRef.current.setData(
      klines.map((k) => ({
        time: k.time as Time,
        value: k.volume,
        color: k.close >= k.open ? 'rgba(34,197,94,0.4)' : 'rgba(239,68,68,0.4)',
      })),
    )

    const closes = klines.map((k) => k.close)
    maSeriesRefs.current.forEach((series, idx) => {
      const { period } = MA_CONFIGS[idx]
      const ma = sma(closes, period)
      const data = klines
        .map((k, i) => ({ time: k.time as Time, value: ma[i] }))
        .filter((p): p is { time: Time; value: number } => p.value !== null)
      series.setData(data)
    })
  }, [klines])

  // 因子数据更新（不调用 fitContent，避免覆盖时间轴联动）
  useEffect(() => {
    if (!factorSeriesRef.current) return
    factorSeriesRef.current.setData(factor.map((f) => ({ time: f.time as Time, value: f.value })))
  }, [factor])

  return (
    <div className="flex flex-col gap-2 h-full">
      <div className="relative flex-1 min-h-0">
        <div className="flex items-center gap-3 mb-1 text-xs">
          <span className="font-semibold text-gray-400 uppercase tracking-wide">K 线</span>
          {MA_CONFIGS.map(({ period, color }) => (
            <span key={period} className="flex items-center gap-1 text-gray-500">
              <span className="inline-block w-3 h-0.5" style={{ backgroundColor: color }} />
              MA{period}
            </span>
          ))}
          <span className="ml-auto text-gray-400">成交量</span>
        </div>
        <div ref={klineRef} className="w-full h-[calc(100%-1.25rem)] border border-gray-100 rounded-lg overflow-hidden" />
        {klineLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/60">
            <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}
      </div>
      <div className="relative flex-1 min-h-0">
        <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">因子副图</div>
        <div ref={factorRef} className="w-full h-[calc(100%-1.25rem)] border border-gray-100 rounded-lg overflow-hidden" />
        {factorLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/60">
            <div className="flex flex-col items-center gap-2">
              <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              <div className="text-xs text-gray-500">AI 正在生成因子…</div>
            </div>
          </div>
        )}
        {!factorLoading && factor.length === 0 && emptyHint && (
          <div className="absolute inset-x-0 top-6 bottom-0 flex items-center justify-center pointer-events-none">
            <p className="text-sm text-gray-400">{emptyHint}</p>
          </div>
        )}
      </div>
    </div>
  )
}
