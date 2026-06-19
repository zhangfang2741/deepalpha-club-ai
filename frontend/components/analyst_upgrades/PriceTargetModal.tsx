'use client'

import { useEffect, useRef, useState } from 'react'
import { X, Loader2 } from 'lucide-react'
import {
  createChart,
  ColorType,
  LineSeries,
  CrosshairMode,
  IChartApi,
  ISeriesApi,
} from 'lightweight-charts'
import { fetchPriceTargetHistory } from '@/lib/api/analyst_upgrade'
import type { PriceTargetQuarter, UpgradeStock } from '@/lib/api/analyst_upgrade'

interface TooltipState {
  visible: boolean
  x: number
  y: number
  label: string
  value: number
  count: number
}

interface ChartPanelProps {
  symbol: string
  quarters: PriceTargetQuarter[]
}

function ChartPanel({ symbol, quarters }: ChartPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const quartersByTime = useRef<Record<number, PriceTargetQuarter>>({})
  const [tooltip, setTooltip] = useState<TooltipState>({
    visible: false, x: 0, y: 0, label: '', value: 0, count: 0,
  })

  useEffect(() => {
    if (!containerRef.current || quarters.length === 0) return

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
      timeScale: { borderVisible: false, tickMarkFormatter: () => '' },
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

    // 季度标签 → unix 时间戳
    const data = quarters.map((q) => {
      const [yearStr, qStr] = q.label.split(' Q')
      const month = (parseInt(qStr) - 1) * 3 + 1
      const ts = Math.floor(new Date(parseInt(yearStr), month - 1, 1).getTime() / 1000)
      quartersByTime.current[ts] = q
      return { time: ts as number, value: q.avg_target }
    })

    series.setData(data as never[])
    chart.timeScale().fitContent()

    // 悬停 tooltip
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
      const q = quartersByTime.current[ts]
      const rect = containerRef.current.getBoundingClientRect()
      setTooltip({
        visible: true,
        x: param.point.x,
        y: param.point.y,
        label: q?.label ?? '',
        value: (price as { value: number }).value,
        count: q?.count ?? 0,
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
  }, [quarters])

  if (quarters.length === 0) {
    return (
      <div className="flex items-center justify-center h-60 text-gray-400 text-sm">
        暂无历史数据
      </div>
    )
  }

  const first = quarters[0]
  const last = quarters[quarters.length - 1]
  const totalPct = first.avg_target > 0
    ? ((last.avg_target - first.avg_target) / first.avg_target * 100).toFixed(1)
    : null

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-4 text-sm">
        <span className="text-gray-500">起点 <span className="font-semibold text-gray-800">${first.avg_target.toFixed(0)}</span> <span className="text-xs text-gray-400">({first.label})</span></span>
        <span className="text-gray-500">最新 <span className="font-semibold text-gray-800">${last.avg_target.toFixed(0)}</span> <span className="text-xs text-gray-400">({last.label})</span></span>
        {totalPct && (
          <span className={`font-semibold ${parseFloat(totalPct) > 0 ? 'text-green-600' : 'text-red-500'}`}>
            区间涨幅 {parseFloat(totalPct) > 0 ? '+' : ''}{totalPct}%
          </span>
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
            <div className="text-gray-400">{tooltip.count} 份报告</div>
          </div>
        )}
      </div>
    </div>
  )
}

interface Props {
  stock: UpgradeStock
  onClose: () => void
}

export default function PriceTargetModal({ stock, onClose }: Props) {
  const [quarters, setQuarters] = useState<PriceTargetQuarter[] | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchPriceTargetHistory(stock.symbol)
      .then((res) => setQuarters(res.quarters))
      .catch(() => setQuarters([]))
      .finally(() => setLoading(false))
  }, [stock.symbol])

  // ESC 关闭
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        {/* 头部 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold text-gray-900">{stock.symbol}</span>
              <span className="text-sm text-gray-500">{stock.name}</span>
            </div>
            <p className="text-xs text-gray-400 mt-0.5">近 5 年分析师平均目标价 · 按季度聚合</p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 快速指标 */}
        <div className="grid grid-cols-4 gap-0 border-b border-gray-100">
          {[
            { label: '近月目标价', value: `$${stock.last_month_target.toFixed(0)}`, sub: `月环比 +${stock.month_mom.toFixed(1)}%`, color: 'text-green-600' },
            { label: '季均目标价', value: `$${stock.last_quarter_target.toFixed(0)}`, sub: `季环比 +${stock.quarter_yoy.toFixed(1)}%`, color: 'text-blue-600' },
            { label: '年均目标价', value: `$${stock.last_year_target.toFixed(0)}`, sub: stock.sector, color: 'text-gray-600' },
            { label: '报告机构数', value: `${stock.last_month_count} 家`, sub: '近一个月', color: 'text-gray-600' },
          ].map((item) => (
            <div key={item.label} className="px-4 py-3 text-center border-r last:border-r-0 border-gray-100">
              <div className={`text-base font-bold ${item.color}`}>{item.value}</div>
              <div className="text-xs text-gray-400 mt-0.5">{item.label}</div>
              <div className="text-xs text-gray-400">{item.sub}</div>
            </div>
          ))}
        </div>

        {/* 图表区 */}
        <div className="px-6 py-5">
          {loading ? (
            <div className="flex items-center justify-center h-60 gap-2 text-gray-400 text-sm">
              <Loader2 className="w-4 h-4 animate-spin" />
              加载历史数据…
            </div>
          ) : quarters !== null ? (
            <ChartPanel symbol={stock.symbol} quarters={quarters} />
          ) : null}
        </div>
      </div>
    </div>
  )
}
