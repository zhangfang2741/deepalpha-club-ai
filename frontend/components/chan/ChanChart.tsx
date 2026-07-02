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
  type IChartApi,
  type ISeriesApi,
  type Time,
  type SeriesMarker,
} from 'lightweight-charts'
import type {
  ChanAnalysisResult,
  Fractal,
  Pivot,
  Signal,
  Stroke,
} from '@/lib/api/chan'

interface Props {
  data: ChanAnalysisResult
  showStrokes?: boolean
  showSegments?: boolean
  showPivots?: boolean
  showSignals?: boolean
  showMacd?: boolean
}

const SIGNAL_COLORS: Record<string, string> = {
  buy1: '#ef4444',
  buy2: '#f97316',
  buy3: '#eab308',
  sell1: '#3b82f6',
  sell2: '#8b5cf6',
  sell3: '#06b6d4',
}

const STRENGTH_SIZE: Record<string, 'small' | 'normal' | 'large'> = {
  strong: 'large',
  medium: 'normal',
  weak: 'small',
}

export function ChanChart({
  data,
  showStrokes = true,
  showSegments = true,
  showPivots = true,
  showSignals = true,
  showMacd = true,
}: Props) {
  const klineRef = useRef<HTMLDivElement>(null)
  const macdRef = useRef<HTMLDivElement>(null)
  const klineChartRef = useRef<IChartApi | null>(null)
  const macdChartRef = useRef<IChartApi | null>(null)

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
      rightPriceScale: { scaleMargins: { top: 0.05, bottom: 0.2 }, minimumWidth: 64 },
    })
    klineChartRef.current = kChart

    // 蜡烛图
    const candleSeries = kChart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderUpColor: '#22c55e',
      borderDownColor: '#ef4444',
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    })

    const bars = data.merged_candles.map((c) => ({
      time: c.time as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }))
    candleSeries.setData(bars)

    // ── 笔（折线标注）───────────────────────────────────────────
    // 已确认的笔用实线（浅虚线），最后一笔若未确认则单独用醒目虚线 + 半透明色，
    // 明确提示“最右侧结构尚未走完”。
    if (showStrokes && data.strokes.length > 0) {
      const confirmedStrokes = data.strokes.filter((s) => s.confirmed)
      const lastStroke = data.strokes[data.strokes.length - 1]
      const lastUnconfirmed = lastStroke && !lastStroke.confirmed

      if (confirmedStrokes.length > 0) {
        const strokeSeries = kChart.addSeries(LineSeries, {
          color: '#f59e0b',
          lineWidth: 1,
          lineStyle: 2, // dashed
          priceLineVisible: false,
          lastValueVisible: false,
        })
        const strokePoints: { time: Time; value: number }[] = []
        for (const stroke of confirmedStrokes) {
          strokePoints.push({ time: stroke.start_time as Time, value: stroke.start_price })
          strokePoints.push({ time: stroke.end_time as Time, value: stroke.end_price })
        }
        const uniq = strokePoints
          .filter((p, i, arr) => arr.findIndex((x) => x.time === p.time) === i)
          .sort((a, b) => (a.time < b.time ? -1 : 1))
        strokeSeries.setData(uniq)
      }

      if (lastUnconfirmed) {
        // 未确认的最后一笔：半透明琥珀色 + 更醒目的点线
        const pendingSeries = kChart.addSeries(LineSeries, {
          color: 'rgba(245,158,11,0.45)',
          lineWidth: 2,
          lineStyle: 1, // dotted
          priceLineVisible: false,
          lastValueVisible: false,
        })
        pendingSeries.setData(
          [
            { time: lastStroke.start_time as Time, value: lastStroke.start_price },
            { time: lastStroke.end_time as Time, value: lastStroke.end_price },
          ].sort((a, b) => (a.time < b.time ? -1 : 1)),
        )
      }
    }

    // ── 线段（更粗实线，级别高于笔）─────────────────────────────
    // 最后一条线段若未确认，用半透明虚线单独绘制，提示其结束尚待确认。
    if (showSegments && data.segments.length > 0) {
      const confirmedSegs = data.segments.filter((s) => s.confirmed)
      const lastSeg = data.segments[data.segments.length - 1]
      const lastSegUnconfirmed = lastSeg && !lastSeg.confirmed

      if (confirmedSegs.length > 0) {
        const segSeries = kChart.addSeries(LineSeries, {
          color: '#10b981',
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: false,
        })
        const segPoints: { time: Time; value: number }[] = []
        for (const seg of confirmedSegs) {
          segPoints.push({ time: seg.start_time as Time, value: seg.start_price })
          segPoints.push({ time: seg.end_time as Time, value: seg.end_price })
        }
        const uniqSeg = segPoints
          .filter((p, i, arr) => arr.findIndex((x) => x.time === p.time) === i)
          .sort((a, b) => (a.time < b.time ? -1 : 1))
        segSeries.setData(uniqSeg)
      }

      if (lastSegUnconfirmed) {
        const pendingSeg = kChart.addSeries(LineSeries, {
          color: 'rgba(16,185,129,0.4)',
          lineWidth: 2,
          lineStyle: 2, // dashed
          priceLineVisible: false,
          lastValueVisible: false,
        })
        pendingSeg.setData(
          [
            { time: lastSeg.start_time as Time, value: lastSeg.start_price },
            { time: lastSeg.end_time as Time, value: lastSeg.end_price },
          ].sort((a, b) => (a.time < b.time ? -1 : 1)),
        )
      }
    }

    // ── 中枢（半透明矩形带 + 加粗边框，醒目标识震荡区）───────────
    if (showPivots) {
      const pivots = [...data.stroke_pivots, ...data.segment_pivots]
      for (const pivot of pivots) {
        const isSeg = pivot.level === 'segment'
        // 未确认中枢：填充更淡、边框改虚线，提示区间仍可能延伸
        const fillColor = pivot.confirmed
          ? isSeg ? 'rgba(168,85,247,0.20)' : 'rgba(59,130,246,0.18)'
          : isSeg ? 'rgba(168,85,247,0.08)' : 'rgba(59,130,246,0.07)'
        const borderColor = isSeg ? '#a855f7' : '#3b82f6'
        const borderStyle = pivot.confirmed ? 0 : 2 // solid | dashed

        // 以 zd 为基线、zg 为顶边，填充 zg~zd 之间形成半透明矩形带
        const bandSeries = kChart.addSeries(BaselineSeries, {
          baseValue: { type: 'price', price: pivot.zd },
          topFillColor1: fillColor,
          topFillColor2: fillColor,
          topLineColor: borderColor,
          bottomFillColor1: 'rgba(0,0,0,0)',
          bottomFillColor2: 'rgba(0,0,0,0)',
          bottomLineColor: 'rgba(0,0,0,0)',
          lineWidth: 2,
          lineStyle: borderStyle,
          priceLineVisible: false,
          lastValueVisible: false,
        })
        bandSeries.setData([
          { time: pivot.start_time as Time, value: pivot.zg },
          { time: pivot.end_time as Time, value: pivot.zg },
        ])

        // 下边框（zd 加粗线）
        const zdSeries = kChart.addSeries(LineSeries, {
          color: borderColor,
          lineWidth: 2,
          lineStyle: borderStyle,
          priceLineVisible: false,
          lastValueVisible: false,
        })
        zdSeries.setData([
          { time: pivot.start_time as Time, value: pivot.zd },
          { time: pivot.end_time as Time, value: pivot.zd },
        ])
      }
    }

    // ── 买卖点标记 ───────────────────────────────────────────
    if (showSignals && data.signals.length > 0) {
      const markers: SeriesMarker<Time>[] = data.signals.map((sig) => ({
        time: sig.time as Time,
        position: sig.is_buy ? 'belowBar' : 'aboveBar',
        color: SIGNAL_COLORS[sig.type] ?? '#ffffff',
        shape: sig.is_buy ? 'arrowUp' : 'arrowDown',
        // 未确认信号追加 "?" 提示其为左侧预判、需后续K线验证
        text: sig.confirmed ? sig.label : `${sig.label}?`,
        size: STRENGTH_SIZE[sig.strength] === 'large' ? 2 : STRENGTH_SIZE[sig.strength] === 'normal' ? 1.5 : 1,
      }))
      createSeriesMarkers(candleSeries, markers)
    }

    // ── MACD 副图 ─────────────────────────────────────────────
    let macdChart: IChartApi | null = null
    if (showMacd && data.macd && macdRef.current) {
      macdChart = createChart(macdRef.current, {
        layout: { background: { color: '#0f172a' }, textColor: '#94a3b8' },
        grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
        crosshair: { mode: CrosshairMode.Normal },
        width: macdRef.current.clientWidth,
        height: macdRef.current.clientHeight,
        timeScale: { rightOffset: 4, barSpacing: 8, fixLeftEdge: true, fixRightEdge: true },
        rightPriceScale: { minimumWidth: 64 },
      })
      macdChartRef.current = macdChart

      // MACD 基于原始K线计算（时间点比合并后的K线多），需对齐到合并K线的时间，
      // 否则两图 X 轴数据点数量不同，基于索引的联动会错位
      const macd = data.macd
      const mergedTimeSet = new Set(data.merged_candles.map((c) => c.time))
      const aligned = macd.times
        .map((t, i) => ({ time: t as Time, dif: macd.dif[i], dea: macd.dea[i], bar: macd.bar[i] }))
        .filter((p) => mergedTimeSet.has(p.time as string))

      const difSeries = macdChart.addSeries(LineSeries, {
        color: '#3b82f6',
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      })
      const deaSeries = macdChart.addSeries(LineSeries, {
        color: '#f97316',
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      })
      const barSeries = macdChart.addSeries(HistogramSeries, {
        priceLineVisible: false,
        lastValueVisible: false,
      })

      difSeries.setData(aligned.map((p) => ({ time: p.time, value: p.dif })))
      deaSeries.setData(aligned.map((p) => ({ time: p.time, value: p.dea })))
      barSeries.setData(
        aligned.map((p) => ({
          time: p.time,
          value: p.bar,
          color: p.bar >= 0 ? 'rgba(34,197,94,0.7)' : 'rgba(239,68,68,0.7)',
        })),
      )

      // 时间轴联动
      const syncKToMacd = () => {
        const range = kChart.timeScale().getVisibleLogicalRange()
        if (range) macdChart?.timeScale().setVisibleLogicalRange(range)
      }
      const syncMacdToK = () => {
        const range = macdChart?.timeScale().getVisibleLogicalRange()
        if (range) kChart.timeScale().setVisibleLogicalRange(range)
      }
      kChart.timeScale().subscribeVisibleLogicalRangeChange(syncKToMacd)
      macdChart.timeScale().subscribeVisibleLogicalRangeChange(syncMacdToK)
    }

    kChart.timeScale().fitContent()

    // ResizeObserver
    const ro = new ResizeObserver(() => {
      if (klineRef.current) kChart.applyOptions({ width: klineRef.current.clientWidth, height: klineRef.current.clientHeight })
      if (macdRef.current && macdChart) macdChart.applyOptions({ width: macdRef.current.clientWidth, height: macdRef.current.clientHeight })
    })
    if (klineRef.current) ro.observe(klineRef.current)
    if (macdRef.current) ro.observe(macdRef.current)

    return () => {
      ro.disconnect()
      kChart.remove()
      macdChart?.remove()
      klineChartRef.current = null
      macdChartRef.current = null
    }
  }, [data, showStrokes, showSegments, showPivots, showSignals, showMacd])

  return (
    <div className="flex flex-col gap-2 h-full">
      <div className="relative flex-[3] min-h-0">
        <div className="text-xs text-slate-500 mb-1 flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-semibold text-slate-400 uppercase tracking-wide">K线 · 缠论结构</span>
          {showStrokes && <span className="flex items-center gap-1"><span className="inline-block w-3 h-0.5 bg-amber-400" />笔</span>}
          {showSegments && <span className="flex items-center gap-1"><span className="inline-block w-3 h-0.5 bg-emerald-500" />线段</span>}
          {showPivots && (
            <>
              <span className="flex items-center gap-1"><span className="inline-block w-3 h-2 rounded-sm bg-blue-500/30 border border-blue-400" />笔级中枢</span>
              <span className="flex items-center gap-1"><span className="inline-block w-3 h-2 rounded-sm bg-purple-500/30 border border-purple-400" />线段级中枢</span>
            </>
          )}
          <span className="flex items-center gap-1 text-slate-500"><span className="inline-block w-3 border-b border-dashed border-slate-400" />虚线/带 ? = 最右侧未确认</span>
        </div>
        <div ref={klineRef} className="w-full h-[calc(100%-1.5rem)] rounded-lg overflow-hidden" />
      </div>
      {showMacd && data.macd && (
        <div className="relative flex-1 min-h-0">
          <div className="text-xs text-slate-500 mb-1 flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-semibold text-slate-400 uppercase tracking-wide">MACD</span>
            <span className="flex items-center gap-1"><span className="inline-block w-3 h-0.5 bg-blue-400" />DIF</span>
            <span className="flex items-center gap-1"><span className="inline-block w-3 h-0.5 bg-orange-400" />DEA</span>
          </div>
          <div ref={macdRef} className="w-full h-[calc(100%-1.5rem)] rounded-lg overflow-hidden" />
        </div>
      )}
    </div>
  )
}
