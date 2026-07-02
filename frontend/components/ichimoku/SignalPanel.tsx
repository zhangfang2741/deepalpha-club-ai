'use client'
import type {
  IchimokuAnalysisResult,
  IchimokuSignal,
  IchimokuState,
  Recommendation,
} from '@/lib/api/ichimoku'

interface Props {
  data: IchimokuAnalysisResult
}

const SIGNAL_STYLE: Record<string, { bg: string; text: string; border: string }> = {
  tk_golden: { bg: 'bg-green-950/40', text: 'text-green-400', border: 'border-green-800' },
  kumo_up: { bg: 'bg-emerald-950/40', text: 'text-emerald-400', border: 'border-emerald-800' },
  tk_dead: { bg: 'bg-red-950/40', text: 'text-red-400', border: 'border-red-800' },
  kumo_down: { bg: 'bg-rose-950/40', text: 'text-rose-400', border: 'border-rose-800' },
}

const STRENGTH_LABEL: Record<string, string> = { strong: '强', medium: '中', weak: '弱' }

const POS_LABEL: Record<string, string> = { above: '云层上方', in: '云层之中', below: '云层下方', na: '数据不足' }
const POS_STYLE: Record<string, string> = {
  above: 'text-green-400',
  below: 'text-red-400',
  in: 'text-amber-400',
  na: 'text-slate-400',
}
const COLOR_LABEL: Record<string, string> = { bullish: '阳云（看涨）', bearish: '阴云（看跌）', na: '未定' }
const TK_LABEL: Record<string, string> = {
  tenkan_above: '转换线在上（偏多）',
  tenkan_below: '转换线在下（偏空）',
  aligned: '转换/基准线粘合',
  na: '数据不足',
}
const CHIKOU_LABEL: Record<string, string> = {
  above: '价格之上（多）',
  below: '价格之下（空）',
  aligned: '持平',
  na: '数据不足',
}

const BIAS_STYLE: Record<string, { bg: string; text: string; border: string; dot: string }> = {
  bullish: { bg: 'bg-green-950/40', text: 'text-green-400', border: 'border-green-800', dot: 'bg-green-400' },
  bearish: { bg: 'bg-red-950/40', text: 'text-red-400', border: 'border-red-800', dot: 'bg-red-400' },
  neutral: { bg: 'bg-slate-800/60', text: 'text-slate-300', border: 'border-slate-700', dot: 'bg-slate-400' },
}

function fmt(v: number | null): string {
  return v === null ? 'N/A' : v.toFixed(2)
}

function StateCard({ state }: { state: IchimokuState }) {
  return (
    <div className="bg-slate-800/60 rounded-lg p-3">
      <div className="text-xs text-slate-500 mb-2 font-semibold">当前状态</div>
      <div className="grid grid-cols-2 gap-y-1.5 gap-x-2 text-xs">
        <span className="text-slate-400">最新价</span>
        <span className="text-right text-slate-100 font-mono">{fmt(state.price)}</span>

        <span className="text-slate-400">价格相对云</span>
        <span className={`text-right font-medium ${POS_STYLE[state.price_vs_cloud]}`}>
          {POS_LABEL[state.price_vs_cloud]}
        </span>

        <span className="text-slate-400">所处云颜色</span>
        <span className={`text-right ${state.cloud_color === 'bullish' ? 'text-green-400' : state.cloud_color === 'bearish' ? 'text-red-400' : 'text-slate-400'}`}>
          {COLOR_LABEL[state.cloud_color]}
        </span>

        <span className="text-slate-400">前方云(未来)</span>
        <span className={`text-right ${state.future_cloud_color === 'bullish' ? 'text-green-400' : state.future_cloud_color === 'bearish' ? 'text-red-400' : 'text-slate-400'}`}>
          {COLOR_LABEL[state.future_cloud_color]}
        </span>

        <span className="text-slate-400">云区间</span>
        <span className="text-right text-slate-300 font-mono">
          {state.cloud_bottom !== null && state.cloud_top !== null
            ? `${fmt(state.cloud_bottom)} ~ ${fmt(state.cloud_top)}`
            : 'N/A'}
        </span>

        <span className="text-slate-400">转换/基准</span>
        <span className="text-right text-slate-300 font-mono">
          {fmt(state.tenkan)} / {fmt(state.kijun)}
        </span>

        <span className="text-slate-400">TK 关系</span>
        <span className="text-right text-slate-300">{TK_LABEL[state.tk_relation]}</span>

        <span className="text-slate-400">迟行线</span>
        <span className="text-right text-slate-300">{CHIKOU_LABEL[state.chikou_relation]}</span>
      </div>
    </div>
  )
}

function SignalCard({ sig }: { sig: IchimokuSignal }) {
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
      <div className={`text-base font-mono font-semibold ${style.text}`}>${sig.price.toFixed(2)}</div>
      <p className="text-xs text-slate-400 mt-1 leading-relaxed">{sig.description}</p>
    </div>
  )
}

function RecommendationCard({ rec }: { rec: Recommendation }) {
  const s = BIAS_STYLE[rec.bias] ?? BIAS_STYLE.neutral
  return (
    <div className={`rounded-lg border p-3 ${s.bg} ${s.border}`}>
      <div className="flex items-center gap-2 mb-2">
        <span className={`inline-block w-2 h-2 rounded-full ${s.dot}`} />
        <span className="text-xs text-slate-500 font-semibold">操作建议</span>
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
  const buyCount = data.signals.filter((s) => s.is_buy).length
  const sellCount = data.signals.filter((s) => !s.is_buy).length

  return (
    <div className="flex flex-col gap-4 lg:h-full lg:overflow-y-auto">
      {data.recommendation && <RecommendationCard rec={data.recommendation} />}

      {data.state && <StateCard state={data.state} />}

      <div className="bg-slate-800/60 rounded-lg p-3">
        <div className="text-xs text-slate-500 mb-1">信号统计</div>
        <div className="grid grid-cols-2 gap-1 text-xs">
          <span className="text-slate-400">看涨信号</span>
          <span className="text-right text-green-400 font-mono">{buyCount}</span>
          <span className="text-slate-400">看跌信号</span>
          <span className="text-right text-red-400 font-mono">{sellCount}</span>
          <span className="text-slate-400">K线数</span>
          <span className="text-right text-slate-200 font-mono">{data.bars_count}</span>
        </div>
      </div>

      {recentSignals.length > 0 ? (
        <div>
          <div className="text-xs font-semibold text-slate-400 mb-2">买卖信号（最近8个）</div>
          <div className="flex flex-col gap-2">
            {recentSignals.map((sig, i) => (
              <SignalCard key={i} sig={sig} />
            ))}
          </div>
        </div>
      ) : (
        <div className="text-center text-slate-500 text-sm py-8">当前时间段未发现明显买卖信号</div>
      )}
    </div>
  )
}
