'use client'
import type { Signal, Pivot, ChanAnalysisResult } from '@/lib/api/chan'

interface Props {
  data: ChanAnalysisResult
}

const SIGNAL_STYLE: Record<string, { bg: string; text: string; border: string }> = {
  buy1: { bg: 'bg-red-950/40', text: 'text-red-400', border: 'border-red-800' },
  buy2: { bg: 'bg-orange-950/40', text: 'text-orange-400', border: 'border-orange-800' },
  buy3: { bg: 'bg-yellow-950/40', text: 'text-yellow-400', border: 'border-yellow-800' },
  sell1: { bg: 'bg-blue-950/40', text: 'text-blue-400', border: 'border-blue-800' },
  sell2: { bg: 'bg-violet-950/40', text: 'text-violet-400', border: 'border-violet-800' },
  sell3: { bg: 'bg-cyan-950/40', text: 'text-cyan-400', border: 'border-cyan-800' },
}

const STRENGTH_LABEL: Record<string, string> = {
  strong: '强',
  medium: '中',
  weak: '弱',
}

function SignalCard({ sig }: { sig: Signal }) {
  const style = SIGNAL_STYLE[sig.type] ?? { bg: 'bg-slate-800', text: 'text-slate-300', border: 'border-slate-700' }
  return (
    <div className={`rounded-lg border p-3 ${style.bg} ${style.border}`}>
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className={`font-bold text-sm ${style.text}`}>{sig.label}</span>
          <span className="text-xs text-slate-500">{STRENGTH_LABEL[sig.strength]}强度</span>
        </div>
        <span className="text-xs text-slate-400">{sig.time}</span>
      </div>
      <div className="flex items-center gap-3">
        <span className={`text-base font-mono font-semibold ${style.text}`}>
          ${sig.price.toFixed(2)}
        </span>
        {sig.area_ratio !== null && (
          <span className="text-xs text-slate-500">
            MACD比={sig.area_ratio.toFixed(2)}
          </span>
        )}
      </div>
      <p className="text-xs text-slate-400 mt-1 line-clamp-2">{sig.description}</p>
    </div>
  )
}

function PivotRow({ pivot }: { pivot: Pivot }) {
  const isSegment = pivot.level === 'segment'
  return (
    <div className={`flex items-center justify-between text-xs py-2 border-b border-slate-800 ${isSegment ? 'text-violet-300' : 'text-blue-300'}`}>
      <div className="flex items-center gap-2">
        <span className={`px-1.5 py-0.5 rounded text-xs font-mono ${isSegment ? 'bg-violet-900/50' : 'bg-blue-900/50'}`}>
          {isSegment ? '线段级' : '笔级'}
        </span>
        <span className="text-slate-400">{pivot.start_time} ~ {pivot.end_time}</span>
      </div>
      <div className="text-right font-mono">
        <span className="text-green-400">ZG {pivot.zg.toFixed(2)}</span>
        <span className="text-slate-500 mx-1">/</span>
        <span className="text-red-400">ZD {pivot.zd.toFixed(2)}</span>
      </div>
    </div>
  )
}

export function SignalPanel({ data }: Props) {
  const recentSignals = [...data.signals].reverse().slice(0, 8)
  const allPivots = [...data.stroke_pivots, ...data.segment_pivots]
    .sort((a, b) => b.start_time.localeCompare(a.start_time))
    .slice(0, 6)

  const buyCount = data.signals.filter((s) => s.is_buy).length
  const sellCount = data.signals.filter((s) => !s.is_buy).length

  return (
    <div className="flex flex-col gap-4 h-full overflow-y-auto">
      {/* 摘要统计 */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-slate-800/60 rounded-lg p-3">
          <div className="text-xs text-slate-500 mb-1">分析结构</div>
          <div className="grid grid-cols-2 gap-1 text-xs">
            <span className="text-slate-400">合并K线</span>
            <span className="text-right text-slate-200 font-mono">{data.merged_candles.length}</span>
            <span className="text-slate-400">分型</span>
            <span className="text-right text-slate-200 font-mono">{data.fractals.length}</span>
            <span className="text-slate-400">笔</span>
            <span className="text-right text-slate-200 font-mono">{data.strokes.length}</span>
            <span className="text-slate-400">线段</span>
            <span className="text-right text-slate-200 font-mono">{data.segments.length}</span>
          </div>
        </div>
        <div className="bg-slate-800/60 rounded-lg p-3">
          <div className="text-xs text-slate-500 mb-1">买卖信号</div>
          <div className="grid grid-cols-2 gap-1 text-xs">
            <span className="text-slate-400">买点</span>
            <span className="text-right text-green-400 font-mono">{buyCount}</span>
            <span className="text-slate-400">卖点</span>
            <span className="text-right text-red-400 font-mono">{sellCount}</span>
            <span className="text-slate-400">笔中枢</span>
            <span className="text-right text-blue-400 font-mono">{data.stroke_pivots.length}</span>
            <span className="text-slate-400">线段中枢</span>
            <span className="text-right text-violet-400 font-mono">{data.segment_pivots.length}</span>
          </div>
        </div>
      </div>

      {/* 当前状态 */}
      {data.current_trend && (
        <div className="bg-slate-800/40 rounded-lg p-3 text-xs text-slate-300">
          <div className="text-slate-500 mb-1 font-semibold">当前状态</div>
          {data.current_trend}
        </div>
      )}

      {/* 近期中枢 */}
      {allPivots.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-slate-400 mb-2">近期中枢</div>
          <div>
            {allPivots.map((p, i) => (
              <PivotRow key={i} pivot={p} />
            ))}
          </div>
        </div>
      )}

      {/* 最近买卖点 */}
      {recentSignals.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-slate-400 mb-2">买卖点信号（最近8个）</div>
          <div className="flex flex-col gap-2">
            {recentSignals.map((sig, i) => (
              <SignalCard key={i} sig={sig} />
            ))}
          </div>
        </div>
      )}

      {recentSignals.length === 0 && (
        <div className="text-center text-slate-500 text-sm py-8">
          当前时间段未发现明显买卖信号
        </div>
      )}
    </div>
  )
}
