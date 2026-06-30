'use client'
import type { Signal, Pivot, Recommendation, ChanAnalysisResult } from '@/lib/api/chan'
import { InfoTip } from './InfoTip'
import {
  CHAN_TERM_MAP,
  SIGNAL_GLOSSARY,
  PIVOT_FIELD_HINT,
  STRENGTH_HINT,
  CURRENT_TREND_HINT,
} from '@/lib/chan-glossary'

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

// 带问号提示的统计标签
function TermLabel({ termKey, label }: { termKey: string; label: string }) {
  const t = CHAN_TERM_MAP[termKey]
  return (
    <span className="flex items-center gap-1 text-slate-400">
      {label}
      {t && <InfoTip title={t.name} content={t.brief} side="left" />}
    </span>
  )
}

function SignalCard({ sig }: { sig: Signal }) {
  const style = SIGNAL_STYLE[sig.type] ?? { bg: 'bg-slate-800', text: 'text-slate-300', border: 'border-slate-700' }
  const glossary = SIGNAL_GLOSSARY[sig.type]
  return (
    <div className={`rounded-lg border p-3 ${style.bg} ${style.border}`}>
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className={`flex items-center gap-1 font-bold text-sm ${style.text}`}>
            {sig.label}
            {glossary && <InfoTip title={glossary.name} content={glossary.detail} side="left" />}
          </span>
          <span className="flex items-center gap-1 text-xs text-slate-500">
            {STRENGTH_LABEL[sig.strength]}强度
            <InfoTip content={STRENGTH_HINT} side="left" />
          </span>
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

const BIAS_STYLE: Record<string, { bg: string; text: string; border: string; dot: string }> = {
  bullish: { bg: 'bg-green-950/40', text: 'text-green-400', border: 'border-green-800', dot: 'bg-green-400' },
  bearish: { bg: 'bg-red-950/40', text: 'text-red-400', border: 'border-red-800', dot: 'bg-red-400' },
  neutral: { bg: 'bg-slate-800/60', text: 'text-slate-300', border: 'border-slate-700', dot: 'bg-slate-400' },
}

function RecommendationCard({ rec }: { rec: Recommendation }) {
  const s = BIAS_STYLE[rec.bias] ?? BIAS_STYLE.neutral
  return (
    <div className={`rounded-lg border p-3 ${s.bg} ${s.border}`}>
      <div className="flex items-center gap-2 mb-2">
        <span className={`inline-block w-2 h-2 rounded-full ${s.dot}`} />
        <span className="text-xs text-slate-500 font-semibold">操作建议</span>
        <InfoTip
          content="综合当前趋势、买卖点信号、背驰、价格相对中枢位置与线段方向得出的技术面参考，非投资建议。"
          side="left"
        />
      </div>
      <div className={`text-base font-bold mb-2 ${s.text}`}>{rec.action_label}</div>
      <ul className="flex flex-col gap-1">
        {rec.reasons.map((r, i) => (
          <li key={i} className="text-xs text-slate-300 flex gap-1.5">
            <span className="text-slate-500 shrink-0">·</span>
            <span>{r}</span>
          </li>
        ))}
      </ul>
      {rec.caveats.length > 0 && (
        <div className="mt-2 pt-2 border-t border-slate-700/50 text-[11px] text-slate-500 leading-relaxed">
          {rec.caveats.join('；')}
        </div>
      )}
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
    <div className="flex flex-col gap-4 lg:h-full lg:overflow-y-auto">
      {/* 操作建议 */}
      {data.recommendation && <RecommendationCard rec={data.recommendation} />}

      {/* 摘要统计 */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-slate-800/60 rounded-lg p-3">
          <div className="text-xs text-slate-500 mb-1">分析结构</div>
          <div className="grid grid-cols-2 gap-1 text-xs">
            <TermLabel termKey="merged" label="合并K线" />
            <span className="text-right text-slate-200 font-mono">{data.merged_candles.length}</span>
            <TermLabel termKey="fractal" label="分型" />
            <span className="text-right text-slate-200 font-mono">{data.fractals.length}</span>
            <TermLabel termKey="stroke" label="笔" />
            <span className="text-right text-slate-200 font-mono">{data.strokes.length}</span>
            <TermLabel termKey="segment" label="线段" />
            <span className="text-right text-slate-200 font-mono">{data.segments.length}</span>
          </div>
        </div>
        <div className="bg-slate-800/60 rounded-lg p-3">
          <div className="flex items-center gap-1 text-xs text-slate-500 mb-1">
            买卖信号
            <InfoTip
              title="三类买卖点"
              content="买卖点按出现顺序分一/二/三类，从背驰反转到突破中枢顺势确认，确认度依次增强。"
              side="left"
            />
          </div>
          <div className="grid grid-cols-2 gap-1 text-xs">
            <span className="text-slate-400">买点</span>
            <span className="text-right text-green-400 font-mono">{buyCount}</span>
            <span className="text-slate-400">卖点</span>
            <span className="text-right text-red-400 font-mono">{sellCount}</span>
            <TermLabel termKey="pivot" label="笔中枢" />
            <span className="text-right text-blue-400 font-mono">{data.stroke_pivots.length}</span>
            <TermLabel termKey="pivot" label="线段中枢" />
            <span className="text-right text-violet-400 font-mono">{data.segment_pivots.length}</span>
          </div>
        </div>
      </div>

      {/* 当前状态 */}
      {data.current_trend && (
        <div className="bg-slate-800/40 rounded-lg p-3 text-xs text-slate-300">
          <div className="flex items-center gap-1 text-slate-500 mb-1 font-semibold">
            当前状态
            <InfoTip title="当前状态" content={CURRENT_TREND_HINT} side="left" />
          </div>
          {data.current_trend}
        </div>
      )}

      {/* 近期中枢 */}
      {allPivots.length > 0 && (
        <div>
          <div className="flex items-center gap-1 text-xs font-semibold text-slate-400 mb-2">
            近期中枢
            <InfoTip content={PIVOT_FIELD_HINT} side="left" />
          </div>
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
