'use client'
import { useEffect, useRef } from 'react'
import {
  createChart,
  createSeriesMarkers,
  CrosshairMode,
  CandlestickSeries,
  LineSeries,
  AreaSeries,
  type IChartApi,
  type Time,
  type SeriesMarker,
} from 'lightweight-charts'
import type { IchimokuAnalysisResult, LinePoint } from '@/lib/api/ichimoku'

interface Props {
  data: IchimokuAnalysisResult
  showTenkan?: boolean
  showKijun?: boolean
  showCloud?: boolean
  showChikou?: boolean
  showSignals?: boolean
}

const SIGNAL_COLORS: Record<string, string> = {
  tk_golden: '#22c55e',
  kumo_up: '#16a34a',
  tk_dead: '#ef4444',
  kumo_down: '#dc2626',
}

const STRENGTH_SIZE: Record<string, number> = { strong: 2, medium: 1.5, weak: 1 }

function toLine(points: LinePoint[]) {
  return points.map((p) => ({ time: p.time as Time, value: p.value }))
}

export function IchimokuChart({
  data,
  showTenkan = true,
  showKijun = true,
  showCloud = true,
  showChikou = true,
  showSignals = true,
}: Props) {
  const chartRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!chartRef.current) return

    const chart = createChart(chartRef.current, {
      layout: { background: { color: '#0f172a' }, textColor: '#94a3b8' },
      grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
      crosshair: { mode: CrosshairMode.Normal },
      width: chartRef.current.clientWidth,
      height: chartRef.current.clientHeight,
      timeScale: { rightOffset: 4, barSpacing: 7, fixLeftEdge: true, fixRightEdge: true },
      rightPriceScale: { scaleMargins: { top: 0.08, bottom: 0.08 }, minimumWidth: 64 },
    })

    // ── 云（Kumo）：先行带 A / B，A 绿 B 棕，附柔和渐变填充营造云层 ──
    // 云要画在最底层，先加填充与边线，再叠加 K 线
    if (showCloud) {
      const aArea = chart.addSeries(AreaSeries, {
        lineColor: 'rgba(34,197,94,0)',
        topColor: 'rgba(34,197,94,0.14)',
        bottomColor: 'rgba(34,197,94,0)',
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      })
      aArea.setData(toLine(data.senkou_a))

      const bArea = chart.addSeries(AreaSeries, {
        lineColor: 'rgba(244,63,94,0)',
        topColor: 'rgba(244,63,94,0.14)',
        bottomColor: 'rgba(244,63,94,0)',
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      })
      bArea.setData(toLine(data.senkou_b))

      const aLine = chart.addSeries(LineSeries, {
        color: '#22c55e',
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      })
      aLine.setData(toLine(data.senkou_a))

      const bLine = chart.addSeries(LineSeries, {
        color: '#b45309',
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      })
      bLine.setData(toLine(data.senkou_b))
    }

    // ── 蜡烛图 ────────────────────────────────────────────────
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderUpColor: '#22c55e',
      borderDownColor: '#ef4444',
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    })
    candleSeries.setData(
      data.candles.map((c) => ({
        time: c.time as Time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    )

    // ── 转换线 Tenkan（蓝）────────────────────────────────────
    if (showTenkan && data.tenkan.length > 0) {
      const s = chart.addSeries(LineSeries, {
        color: '#3b82f6',
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      })
      s.setData(toLine(data.tenkan))
    }

    // ── 基准线 Kijun（红）─────────────────────────────────────
    if (showKijun && data.kijun.length > 0) {
      const s = chart.addSeries(LineSeries, {
        color: '#ef4444',
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      })
      s.setData(toLine(data.kijun))
    }

    // ── 迟行线 Chikou（紫，后移）──────────────────────────────
    if (showChikou && data.chikou.length > 0) {
      const s = chart.addSeries(LineSeries, {
        color: '#a855f7',
        lineWidth: 1,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      })
      s.setData(toLine(data.chikou))
    }

    // ── 买卖信号标记 ──────────────────────────────────────────
    if (showSignals && data.signals.length > 0) {
      const markers: SeriesMarker<Time>[] = data.signals.map((sig) => ({
        time: sig.time as Time,
        position: sig.is_buy ? 'belowBar' : 'aboveBar',
        color: SIGNAL_COLORS[sig.type] ?? '#ffffff',
        shape: sig.is_buy ? 'arrowUp' : 'arrowDown',
        text: sig.label,
        size: STRENGTH_SIZE[sig.strength] ?? 1,
      }))
      createSeriesMarkers(candleSeries, markers)
    }

    chart.timeScale().fitContent()

    const ro = new ResizeObserver(() => {
      if (chartRef.current)
        chart.applyOptions({ width: chartRef.current.clientWidth, height: chartRef.current.clientHeight })
    })
    ro.observe(chartRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
    }
  }, [data, showTenkan, showKijun, showCloud, showChikou, showSignals])

  return (
    <div className="flex flex-col gap-2 h-full">
      <div className="text-xs text-slate-500 flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-semibold text-slate-400 uppercase tracking-wide">一目均衡表</span>
        {showTenkan && <Legend color="bg-blue-500" label="转换线" />}
        {showKijun && <Legend color="bg-red-500" label="基准线" />}
        {showCloud && (
          <>
            <Legend color="bg-green-500" label="先行带A" />
            <Legend color="bg-amber-700" label="先行带B" />
            <span className="flex items-center gap-1">
              <span className="inline-block w-3 h-2 rounded-sm bg-green-500/20 border border-green-500/40" />云(阳/阴)
            </span>
          </>
        )}
        {showChikou && <Legend color="bg-purple-500" label="迟行线" dashed />}
      </div>
      <div ref={chartRef} className="w-full flex-1 min-h-0 rounded-lg overflow-hidden" />
    </div>
  )
}

function Legend({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`inline-block w-3 h-0.5 ${color} ${dashed ? 'opacity-70' : ''}`} />
      {label}
    </span>
  )
}
