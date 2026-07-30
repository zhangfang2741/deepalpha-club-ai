'use client'

import { useEffect, useState, useCallback } from 'react'
import Spinner from '@/components/ui/Spinner'
import { LABEL_COLOR, labelZh, colorOf } from '@/components/regime/common'
import {
  fetchRegime,
  triggerRegimeStage,
  type RegimePoint,
  type RegimeResponse,
} from '@/lib/api/regime'

const RANGE_OPTIONS = [
  { label: '3个月', limit: 90 },
  { label: '6个月', limit: 180 },
  { label: '1年', limit: 250 },
  { label: '2年', limit: 500 },
]

const STATE_DESC: Record<string, string> = {
  risk_on: '资金正涌入进攻板块，市场处于逐利模式，风险偏好偏高。',
  neutral: '进攻与防御力量相当，市场观望，方向尚未明朗。',
  risk_off: '资金正撤向防御与现金，市场进入避险模式，回撤风险上升。',
}

type Tone = 'riskon' | 'riskoff' | 'warn' | 'neutral'
const TONE_COLOR: Record<Tone, string> = {
  riskon: '#dc2626',
  riskoff: '#16a34a',
  warn: '#d97706',
  neutral: '#64748b',
}

function weightAdvice(fw: number | null): { text: string; tone: Tone } {
  if (fw === null) return { text: '历史不足，暂不给出建议', tone: 'neutral' }
  if (fw >= 0.7) return { text: '进攻 / 动量类因子可正常持有', tone: 'riskon' }
  if (fw >= 0.4) return { text: '建议对动量类因子适度降权', tone: 'warn' }
  return { text: '建议显著降低动量 / 成长类仓位', tone: 'riskoff' }
}

type Verdict = { text: string; tone: Tone }
function odsVerdict(v: number | null): Verdict {
  if (v === null) return { text: '—', tone: 'neutral' }
  if (v > 0.02) return { text: '进攻占优', tone: 'riskon' }
  if (v < -0.02) return { text: '防御占优', tone: 'riskoff' }
  return { text: '大致均衡', tone: 'neutral' }
}
function cfVerdict(v: number | null): Verdict {
  if (v === null) return { text: '—', tone: 'neutral' }
  if (v > 0.01) return { text: '资金离场', tone: 'riskoff' }
  if (v < -0.01) return { text: '留在风险资产', tone: 'riskon' }
  return { text: '大致均衡', tone: 'neutral' }
}
function vixVerdict(v: number | null): Verdict {
  if (v === null) return { text: '—', tone: 'neutral' }
  if (v < 16) return { text: '情绪平静', tone: 'riskon' }
  if (v > 24) return { text: '情绪紧张', tone: 'riskoff' }
  return { text: '情绪中性', tone: 'warn' }
}
function cmfVerdict(v: number | null): Verdict {
  if (v === null) return { text: '—', tone: 'neutral' }
  if (v > 0.02) return { text: '资金流入', tone: 'riskon' }
  if (v < -0.02) return { text: '资金流出', tone: 'riskoff' }
  return { text: '进出均衡', tone: 'neutral' }
}

function yearBoundaries(dates: string[]): number[] {
  const out: number[] = []
  let lastYear = ''
  dates.forEach((d, i) => {
    const y = d.slice(0, 4)
    if (y !== lastYear) {
      if (lastYear !== '') out.push(i)
      lastYear = y
    }
  })
  return out
}

function TimeAxis({ dates }: { dates: string[] }) {
  if (dates.length < 2) return null
  const n = dates.length
  const ticks = 5
  const idxs = Array.from({ length: ticks }, (_, k) => Math.round((k / (ticks - 1)) * (n - 1)))
  return (
    <div className="relative h-4 mt-1.5 select-none">
      {idxs.map((i, k) => {
        const pct = (i / (n - 1)) * 100
        const lbl = dates[i].slice(0, 7)
        const style: React.CSSProperties =
          k === 0 ? { left: '0%' } : k === ticks - 1 ? { right: '0%' } : { left: `${pct}%`, transform: 'translateX(-50%)' }
        return (
          <span key={i} className="absolute top-0 text-[10px] text-gray-400 font-mono tabular-nums whitespace-nowrap" style={style}>
            {lbl}
          </span>
        )
      })}
    </div>
  )
}

function StateMeter({ on, neu, off }: { on: number | null; neu: number | null; off: number | null }) {
  if (on === null || neu === null || off === null) {
    return <div className="text-sm text-white/70">历史不足，尚无状态后验</div>
  }
  const segs = [
    { k: '逐利', v: on, c: LABEL_COLOR.risk_on },
    { k: '观望', v: neu, c: LABEL_COLOR.neutral },
    { k: '避险', v: off, c: LABEL_COLOR.risk_off },
  ]
  return (
    <div className="flex flex-col gap-2">
      <div className="flex h-4 w-full overflow-hidden rounded-full bg-white/25">
        {segs.map((s) => (
          <div key={s.k} style={{ width: `${(s.v * 100).toFixed(1)}%`, background: s.c }} className="h-full transition-all duration-500" />
        ))}
      </div>
      <div className="flex justify-between text-xs font-semibold">
        {segs.map((s) => (
          <span key={s.k} className="flex items-center gap-1.5 text-white/90">
            <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: s.c }} />
            {s.k} <span className="font-mono tabular-nums">{Math.round(s.v * 100)}%</span>
          </span>
        ))}
      </div>
    </div>
  )
}

function SignalRow({ name, meaning, value, verdict }: { name: string; meaning: string; value: string; verdict: Verdict }) {
  return (
    <div className="flex items-center gap-3 py-3 border-b border-gray-100 last:border-0">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-bold text-gray-800">{name}</div>
        <div className="text-xs text-gray-400 truncate">{meaning}</div>
      </div>
      <div className="font-mono tabular-nums text-sm font-semibold text-gray-700 w-16 text-right">{value}</div>
      <span
        className="text-xs font-bold px-2.5 py-1 rounded-lg whitespace-nowrap w-24 text-center"
        style={{ color: TONE_COLOR[verdict.tone], background: `${TONE_COLOR[verdict.tone]}14` }}
      >
        {verdict.text}
      </span>
    </div>
  )
}

function Sparkline({ values, dates, color, height = 48, zeroLine = false }: { values: (number | null)[]; dates: string[]; color: string; height?: number; zeroLine?: boolean }) {
  const nums = values.filter((v): v is number => v !== null && !Number.isNaN(v))
  if (nums.length < 2) return <div className="text-xs text-gray-400">暂无数据</div>
  const min = Math.min(...nums)
  const max = Math.max(...nums)
  const span = max - min || 1
  const w = 100
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * w
    const y = v === null || Number.isNaN(v) ? null : height - ((v - min) / span) * height
    return { x, y }
  })
  let d = ''
  pts.forEach((p) => {
    if (p.y === null) return
    d += d === '' ? `M ${p.x} ${p.y}` : ` L ${p.x} ${p.y}`
  })
  const zeroY = zeroLine && min < 0 && max > 0 ? height - ((0 - min) / span) * height : null
  const lastPt = [...pts].reverse().find((p) => p.y !== null)
  const years = yearBoundaries(dates)
  return (
    <>
      <svg viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" className="w-full" style={{ height }}>
        {years.map((i) => {
          const x = (i / (values.length - 1)) * w
          return <line key={i} x1={x} y1={0} x2={x} y2={height} stroke="currentColor" className="text-gray-200" strokeWidth={0.5} />
        })}
        {zeroY !== null && <line x1={0} y1={zeroY} x2={w} y2={zeroY} stroke="#cbd5e1" strokeWidth={0.5} strokeDasharray="2 2" />}
        <path d={d} fill="none" stroke={color} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        {lastPt && lastPt.y !== null && <circle cx={lastPt.x} cy={lastPt.y} r={1.6} fill={color} vectorEffect="non-scaling-stroke" />}
      </svg>
      <TimeAxis dates={dates} />
    </>
  )
}

function PosteriorStack({ history }: { history: RegimePoint[] }) {
  const rows = history.filter((p) => p.p_risk_off !== null)
  if (rows.length < 2) {
    return <div className="text-sm text-gray-400 py-8 text-center">历史不足，尚无后验（需≥1年历史拟合 HMM）</div>
  }
  const w = 100
  const h = 120
  const n = rows.length
  const dates = rows.map((p) => p.trade_date)
  const buildArea = (getBottom: (p: RegimePoint) => number, getTop: (p: RegimePoint) => number) => {
    const top = rows.map((p, i) => `${(i / (n - 1)) * w},${h - getTop(p) * h}`)
    const bottom = rows.map((p, i) => `${(i / (n - 1)) * w},${h - getBottom(p) * h}`).reverse()
    return `M ${top.join(' L ')} L ${bottom.join(' L ')} Z`
  }
  const off = (p: RegimePoint) => p.p_risk_off ?? 0
  const neu = (p: RegimePoint) => (p.p_risk_off ?? 0) + (p.p_neutral ?? 0)
  const on = () => 1
  const years = yearBoundaries(dates)
  return (
    <>
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="w-full" style={{ height: 160 }}>
        <path d={buildArea(() => 0, off)} fill={LABEL_COLOR.risk_off} opacity={0.85} />
        <path d={buildArea(off, neu)} fill={LABEL_COLOR.neutral} opacity={0.85} />
        <path d={buildArea(neu, on)} fill={LABEL_COLOR.risk_on} opacity={0.85} />
        {years.map((i) => {
          const x = (i / (n - 1)) * w
          return <line key={i} x1={x} y1={0} x2={x} y2={h} stroke="#ffffff" strokeOpacity={0.35} strokeWidth={0.5} />
        })}
      </svg>
      <TimeAxis dates={dates} />
    </>
  )
}

function fmt(value: number | null, digits = 2): string {
  return value === null ? '—' : value.toFixed(digits)
}

function ChartCard({ title, color, children }: { title: string; color: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-sm font-bold mb-3" style={{ color }}>
        {title}
      </h3>
      {children}
    </div>
  )
}

function Legend({ color, text }: { color: string; text: string }) {
  return (
    <span className="flex items-center gap-1 text-gray-500">
      <span className="w-3 h-3 rounded-sm" style={{ background: color }} />
      {text}
    </span>
  )
}

/**
 * 大盘市场状态面板（regime）：可嵌入任意页面（如恐慌指数页）。
 */
export default function MarketRegimePanel() {
  const [data, setData] = useState<RegimeResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [limit, setLimit] = useState(250)
  const [showAdvanced, setShowAdvanced] = useState(false)

  const load = useCallback(async (lim: number) => {
    setLoading(true)
    setError(null)
    try {
      setData(await fetchRegime(lim))
    } catch {
      setError('加载市场状态失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(limit)
  }, [load, limit])

  const handleRun = async () => {
    setRunning(true)
    setError(null)
    try {
      await triggerRegimeStage()
      await load(limit)
    } catch {
      setError('重新计算失败（需登录且行情可用）')
    } finally {
      setRunning(false)
    }
  }

  const latest = data?.latest ?? null
  const curLabel = latest ? latest.confirmed_label ?? latest.regime_label : null
  const heroColor = colorOf(curLabel)
  const advice = weightAdvice(latest?.factor_weight ?? null)

  let lastSwitch: { date: string; from: string; to: string } | null = null
  if (data) {
    const confirmed = data.history.filter((p) => p.confirmed_label)
    for (let i = confirmed.length - 1; i > 0; i--) {
      if (confirmed[i].confirmed_label !== confirmed[i - 1].confirmed_label) {
        lastSwitch = { date: confirmed[i].trade_date, from: confirmed[i - 1].confirmed_label!, to: confirmed[i].confirmed_label! }
        break
      }
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <p className="text-sm text-gray-500 leading-relaxed">
          三篮子资金流（ODS/CF）+ 真拟合 HMM，判断大盘是<span className="font-semibold text-red-600">逐利</span>、
          <span className="font-semibold text-amber-600">观望</span>还是<span className="font-semibold text-green-600">避险</span>，并给出因子仓位建议。
        </p>
        <button
          onClick={handleRun}
          disabled={running}
          className="px-4 py-2 rounded-xl bg-gray-900 text-white text-sm font-bold hover:bg-gray-800 disabled:opacity-50 transition-all whitespace-nowrap"
        >
          {running ? '计算中…' : '重新计算'}
        </button>
      </div>

      {error && <div className="px-4 py-3 rounded-xl bg-red-50 border border-red-100 text-red-600 text-sm font-medium">{error}</div>}
      {loading && !data && (
        <div className="flex items-center justify-center h-[240px]">
          <Spinner size={40} />
        </div>
      )}

      {latest && (
        <div className="rounded-3xl p-7 text-white shadow-lg relative overflow-hidden" style={{ background: `linear-gradient(135deg, ${heroColor} 0%, ${heroColor}cc 100%)` }}>
          <div className="relative flex flex-col lg:flex-row lg:items-center gap-6">
            <div className="flex-1">
              <div className="text-xs font-bold uppercase tracking-widest text-white/70 mb-2">当前大盘状态</div>
              <div className="flex items-baseline gap-3 flex-wrap">
                <span className="text-5xl font-black tracking-tight">{labelZh(curLabel)}</span>
                <span className="text-sm font-semibold text-white/80 bg-white/15 px-2.5 py-1 rounded-lg">
                  {latest.confirmed_label ? '已确认' : latest.regime_label ? '待确认' : '数据不足'}
                </span>
              </div>
              <p className="mt-3 text-base text-white/90 leading-relaxed max-w-xl">{curLabel ? STATE_DESC[curLabel] : '历史数据不足，尚未拟合出市场状态。'}</p>
              <div className="mt-2 text-xs text-white/60 font-mono">{latest.trade_date} · 参数版本 {latest.params_version ?? '—'}</div>
            </div>
            <div className="lg:w-80 flex flex-col gap-4">
              <StateMeter on={latest.p_risk_on} neu={latest.p_neutral} off={latest.p_risk_off} />
              <div className="bg-white/15 rounded-2xl p-4 backdrop-blur-sm">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-white/70 uppercase tracking-wider">因子仓位系数</span>
                  <span className="text-3xl font-black font-mono tabular-nums">{latest.factor_weight === null ? '—' : latest.factor_weight.toFixed(2)}</span>
                </div>
                <div className="text-xs text-white/80 mt-1.5 leading-snug">{advice.text}</div>
                <div className="text-[11px] text-white/50 mt-1">1 = 满仓，0 = 空仓 · 越低说明越该回避风险</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {lastSwitch && (
        <div className="flex items-center gap-2 text-sm bg-white rounded-xl border border-gray-100 px-4 py-3 shadow-sm">
          <span className="text-gray-400 font-medium">最近一次状态切换</span>
          <span className="font-mono text-gray-500">{lastSwitch.date}</span>
          <span className="font-bold" style={{ color: colorOf(lastSwitch.from) }}>{labelZh(lastSwitch.from)}</span>
          <span className="text-gray-400">→</span>
          <span className="font-bold" style={{ color: colorOf(lastSwitch.to) }}>{labelZh(lastSwitch.to)}</span>
        </div>
      )}

      {latest && (
        <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm">
          <div className="flex items-baseline justify-between mb-2">
            <h2 className="text-base font-bold text-gray-800">信号解读</h2>
            <span className="text-xs text-gray-400">四路指标各自的结论，综合得出上面的状态</span>
          </div>
          <SignalRow name="进攻 vs 防御（ODS）" meaning="进攻板块相对防御板块的强弱" value={fmt(latest.ods, 3)} verdict={odsVerdict(latest.ods)} />
          <SignalRow name="现金 vs 风险资产（CF）" meaning="资金是否整体撤向现金" value={fmt(latest.cf, 3)} verdict={cfVerdict(latest.cf)} />
          <SignalRow name="市场情绪（VIX）" meaning="隐含波动率，越高越恐慌" value={fmt(latest.vix, 1)} verdict={vixVerdict(latest.vix)} />
          <SignalRow name="资金进出（CMF）" meaning="纳指的量价资金流向" value={fmt(latest.cmf, 3)} verdict={cmfVerdict(latest.cmf)} />
        </div>
      )}

      <div className="flex items-center gap-1.5 bg-gray-100/70 p-1 rounded-xl w-fit">
        {RANGE_OPTIONS.map((r) => (
          <button
            key={r.limit}
            onClick={() => setLimit(r.limit)}
            className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${limit === r.limit ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-900'}`}
          >
            {r.label}
          </button>
        ))}
      </div>

      {data && !loading && (
        <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm">
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-base font-bold text-gray-800">状态演变</h2>
            <div className="flex items-center gap-3 text-xs font-semibold">
              <Legend color={LABEL_COLOR.risk_on} text="逐利" />
              <Legend color={LABEL_COLOR.neutral} text="观望" />
              <Legend color={LABEL_COLOR.risk_off} text="避险" />
            </div>
          </div>
          <p className="text-xs text-gray-400 mb-3">每一天三种状态的概率占比，色块越厚说明该状态越主导</p>
          <PosteriorStack history={data.history} />
        </div>
      )}

      {data && !loading && (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
          <button onClick={() => setShowAdvanced((v) => !v)} className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-gray-50 transition-colors">
            <span className="text-base font-bold text-gray-800">原始信号趋势（进阶）</span>
            <span className="text-sm text-gray-400">{showAdvanced ? '收起 ▲' : '展开 ▼'}</span>
          </button>
          {showAdvanced && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 px-6 pb-6">
              <ChartCard title="ODS · 进攻−防御" color="#7c3aed">
                <Sparkline values={data.history.map((p) => p.ods)} dates={data.history.map((p) => p.trade_date)} color="#7c3aed" zeroLine />
              </ChartCard>
              <ChartCard title="CF · 现金−风险资产" color="#0891b2">
                <Sparkline values={data.history.map((p) => p.cf)} dates={data.history.map((p) => p.trade_date)} color="#0891b2" zeroLine />
              </ChartCard>
              <ChartCard title="VIX · 波动率" color="#dc2626">
                <Sparkline values={data.history.map((p) => p.vix)} dates={data.history.map((p) => p.trade_date)} color="#dc2626" />
              </ChartCard>
              <ChartCard title="CMF · 量价资金流" color="#16a34a">
                <Sparkline values={data.history.map((p) => p.cmf)} dates={data.history.map((p) => p.trade_date)} color="#16a34a" zeroLine />
              </ChartCard>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
