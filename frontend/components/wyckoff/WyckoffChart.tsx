'use client'
import { useEffect, useRef } from 'react'
import {
  createChart,
  createSeriesMarkers,
  CrosshairMode,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  BaselineSeries,
  LineStyle,
  type IChartApi,
  type Time,
  type SeriesMarker,
} from 'lightweight-charts'
import type { WyckoffAnalysisResult } from '@/lib/api/wyckoff'

// 成交量坐标轴紧凑格式化（避免长数字撑宽坐标轴导致量价不对齐）
function formatVolume(v: number): string {
  if (v >= 1e9) return (v / 1e9).toFixed(1) + 'B'
  if (v >= 1e6) return (v / 1e6).toFixed(0) + 'M'
  if (v >= 1e3) return (v / 1e3).toFixed(0) + 'K'
  return String(Math.round(v))
}

interface Props {
  data: WyckoffAnalysisResult
  showRange?: boolean
  showEvents?: boolean
  showVolume?: boolean
}

// 偏空事件（顶部标记）；其余视为偏多/中性事件（底部标记）
const BEARISH_EVENTS = new Set(['BC', 'UT', 'UTAD', 'SOW', 'LPSY', 'PSY'])

const EVENT_COLOR: Record<string, string> = {
  SC: '#ef4444',
  AR: '#38bdf8',
  ST: '#eab308',
  SPRING: '#22c55e',
  TEST: '#84cc16',
  SOS: '#10b981',
  LPS: '#34d399',
  BU: '#2dd4bf',
  PS: '#f97316',
  PSY: '#f97316',
  BC: '#ef4444',
  UT: '#f43f5e',
  UTAD: '#e11d48',
  SOW: '#dc2626',
  LPSY: '#fb7185',
}

export function WyckoffChart({
  data,
  showRange = true,
  showEvents = true,
  showVolume = true,
}: Props) {
  const klineRef = useRef<HTMLDivElement>(null)
  const volRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!klineRef.current) return

    // ── 主图 ──────────────────────────────────────────────────
    const kChart = createChart(klineRef.current, {
      layout: { background: { color: '#0f172a' }, textColor: '#94a3b8' },
      grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
      crosshair: { mode: CrosshairMode.Normal },
      width: klineRef.current.clientWidth,
      height: klineRef.current.clientHeight,
      timeScale: { rightOffset: 4, barSpacing: 8, fixLeftEdge: true, fixRightEdge: true },
      rightPriceScale: { scaleMargins: { top: 0.05, bottom: 0.1 }, minimumWidth: 64 },
    })

    const candleSeries = kChart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderUpColor: '#22c55e',
      borderDownColor: '#ef4444',
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    })

    const bars = data.candles.map((c) => ({
      time: c.time as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }))
    candleSeries.setData(bars)

    // ── 交易区间（半透明矩形带 + 支撑/阻力边框）──────────────────
    const tr = data.trading_range
    if (showRange && tr && data.candles.length > 0) {
      const isAcc = tr.kind === 'accumulation'
      const fillColor = isAcc ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)'
      const borderColor = isAcc ? '#22c55e' : '#ef4444'
      const startTime = tr.start_time as Time
      const endTime = data.candles[data.candles.length - 1].time as Time

      const bandSeries = kChart.addSeries(BaselineSeries, {
        baseValue: { type: 'price', price: tr.support },
        topFillColor1: fillColor,
        topFillColor2: fillColor,
        topLineColor: borderColor,
        bottomFillColor1: 'rgba(0,0,0,0)',
        bottomFillColor2: 'rgba(0,0,0,0)',
        bottomLineColor: 'rgba(0,0,0,0)',
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      })
      bandSeries.setData([
        { time: startTime, value: tr.resistance },
        { time: endTime, value: tr.resistance },
      ])

      const supportSeries = kChart.addSeries(LineSeries, {
        color: borderColor,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      })
      supportSeries.setData([
        { time: startTime, value: tr.support },
        { time: endTime, value: tr.support },
      ])

      // 区间上沿/下沿价格标注，明确「具体是哪个区间」
      candleSeries.createPriceLine({
        price: tr.resistance,
        color: borderColor,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: `区间上沿 ${tr.resistance.toFixed(2)}`,
      })
      candleSeries.createPriceLine({
        price: tr.support,
        color: borderColor,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: `区间下沿 ${tr.support.toFixed(2)}`,
      })
    }

    // ── 威科夫事件标记 ─────────────────────────────────────────
    if (showEvents && data.events.length > 0) {
      const markers: SeriesMarker<Time>[] = data.events.map((e) => {
        const bearish = BEARISH_EVENTS.has(e.code)
        return {
          time: e.time as Time,
          position: bearish ? 'aboveBar' : 'belowBar',
          color: EVENT_COLOR[e.code] ?? '#ffffff',
          shape: bearish ? 'arrowDown' : 'arrowUp',
          text: e.name,
        }
      })
      createSeriesMarkers(candleSeries, markers)
    }

    // ── 成交量副图 ─────────────────────────────────────────────
    let volChart: IChartApi | null = null
    if (showVolume && volRef.current) {
      volChart = createChart(volRef.current, {
        layout: { background: { color: '#0f172a' }, textColor: '#94a3b8' },
        grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
        crosshair: { mode: CrosshairMode.Normal },
        width: volRef.current.clientWidth,
        height: volRef.current.clientHeight,
        timeScale: { rightOffset: 4, barSpacing: 8, fixLeftEdge: true, fixRightEdge: true },
        // 与主图价格轴同宽（minimumWidth 一致）+ 紧凑量能格式，保证量价对齐
        rightPriceScale: { minimumWidth: 64 },
        localization: { priceFormatter: formatVolume },
      })

      const volSeries = volChart.addSeries(HistogramSeries, {
        priceLineVisible: false,
        lastValueVisible: false,
      })
      volSeries.setData(
        data.candles.map((c) => ({
          time: c.time as Time,
          value: c.volume,
          color: c.close >= c.open ? 'rgba(34,197,94,0.6)' : 'rgba(239,68,68,0.6)',
        })),
      )

      // 时间轴联动
      const syncKToVol = () => {
        const range = kChart.timeScale().getVisibleLogicalRange()
        if (range) volChart?.timeScale().setVisibleLogicalRange(range)
      }
      const syncVolToK = () => {
        const range = volChart?.timeScale().getVisibleLogicalRange()
        if (range) kChart.timeScale().setVisibleLogicalRange(range)
      }
      kChart.timeScale().subscribeVisibleLogicalRangeChange(syncKToVol)
      volChart.timeScale().subscribeVisibleLogicalRangeChange(syncVolToK)
    }

    kChart.timeScale().fitContent()

    // 初始化时把主图可视区间同步给成交量副图，避免两图起始/结束不一致
    if (volChart) {
      const initRange = kChart.timeScale().getVisibleLogicalRange()
      if (initRange) volChart.timeScale().setVisibleLogicalRange(initRange)
    }

    const ro = new ResizeObserver(() => {
      if (klineRef.current) kChart.applyOptions({ width: klineRef.current.clientWidth, height: klineRef.current.clientHeight })
      if (volRef.current && volChart) volChart.applyOptions({ width: volRef.current.clientWidth, height: volRef.current.clientHeight })
    })
    if (klineRef.current) ro.observe(klineRef.current)
    if (volRef.current) ro.observe(volRef.current)

    return () => {
      ro.disconnect()
      kChart.remove()
      volChart?.remove()
    }
  }, [data, showRange, showEvents, showVolume])

  return (
    <div className="flex flex-col gap-2 h-full">
      <div className="relative flex-[3] min-h-0">
        <div className="text-xs text-slate-500 mb-1 flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-semibold text-slate-400 uppercase tracking-wide">K线 · 威科夫结构</span>
          {showRange && data.trading_range && (
            <span className="flex items-center gap-1">
              <span
                className={`inline-block w-3 h-2 rounded-sm border ${
                  data.trading_range.kind === 'accumulation'
                    ? 'bg-emerald-500/20 border-emerald-400'
                    : 'bg-red-500/20 border-red-400'
                }`}
              />
              {data.trading_range.kind === 'accumulation' ? '吸筹区间' : '派发区间'}
            </span>
          )}
          {showEvents && <span className="text-slate-500">▲/▼ 威科夫事件</span>}
        </div>
        <div ref={klineRef} className="w-full h-[calc(100%-1.5rem)] rounded-lg overflow-hidden" />
      </div>
      {showVolume && (
        <div className="relative flex-1 min-h-0">
          <div className="text-xs text-slate-500 mb-1 flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-semibold text-slate-400 uppercase tracking-wide">成交量</span>
          </div>
          <div ref={volRef} className="w-full h-[calc(100%-1.5rem)] rounded-lg overflow-hidden" />
        </div>
      )}
    </div>
  )
}
