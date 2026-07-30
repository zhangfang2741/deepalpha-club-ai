'use client'

import { useEffect, useState, useCallback } from 'react'
import DashboardShell from '@/components/layout/DashboardShell'
import Spinner from '@/components/ui/Spinner'
import {
  fetchRegime,
  triggerRegimeStage,
  fetchSectorRegimes,
  REGIME_LABEL_ZH,
  type RegimePoint,
  type RegimeResponse,
  type SectorRegimePoint,
} from '@/lib/api/regime'

const RANGE_OPTIONS = [
  { label: '3个月', limit: 90 },
  { label: '6个月', limit: 180 },
  { label: '1年', limit: 250 },
  { label: '2年', limit: 500 },
]

// 状态配色（A 股约定：红=贪婪/逐利，绿=恐慌/避险，与全站恐慌指数一致）
const LABEL_COLOR: Record<string, string> = {
  risk_on: '#dc2626', // 逐利 红（贪婪）
  neutral: '#d97706', // 观望 橙
  risk_off: '#16a34a', // 避险 绿（恐慌）
}
const NEUTRAL_COLOR = '#64748b'

// 一句话解读：市场此刻在做什么
const STATE_DESC: Record<string, string> = {
  risk_on: '资金正涌入进攻板块，市场处于逐利模式，风险偏好偏高。',
  neutral: '进攻与防御力量相当，市场观望，方向尚未明朗。',
  risk_off: '资金正撤向防御与现金，市场进入避险模式，回撤风险上升。',
}

function labelZh(label: string | null): string {
  if (!label) return '数据不足'
  return REGIME_LABEL_ZH[label] ?? label
}

function colorOf(label: string | null): string {
  return label ? LABEL_COLOR[label] ?? NEUTRAL_COLOR : NEUTRAL_COLOR
}

// factor_weight → 给下游动量类因子的建议动作
function weightAdvice(fw: number | null): { text: string; tone: Tone } {
  if (fw === null) return { text: '历史不足，暂不给出建议', tone: 'neutral' }
  if (fw >= 0.7) return { text: '进攻 / 动量类因子可正常持有', tone: 'riskon' }
  if (fw >= 0.4) return { text: '建议对动量类因子适度降权', tone: 'warn' }
  return { text: '建议显著降低动量 / 成长类仓位', tone: 'riskoff' }
}

// tone 按风险方向着色：riskon=红（贪婪/进攻），riskoff=绿（恐慌/避险）
type Tone = 'riskon' | 'riskoff' | 'warn' | 'neutral'
const TONE_COLOR: Record<Tone, string> = {
  riskon: '#dc2626',
  riskoff: '#16a34a',
  warn: '#d97706',
  neutral: '#64748b',
}

// ── 信号 → 人话判定 ─────────────────────────────────────────────
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

// 年份分界的索引（用于 X 轴网格线）
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

// X 轴时间刻度（等距 5 个）
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

// ── 单条三色概率条（替代三根分离 bar，一眼看清主导状态） ────────
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

// ── 信号解读行 ─────────────────────────────────────────────────
function SignalRow({
  name,
  meaning,
  value,
  verdict,
}: {
  name: string
  meaning: string
  value: string
  verdict: Verdict
}) {
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

// ── 内联 SVG 折线图（带 X 时间轴） ──────────────────────────────
function Sparkline({
  values,
  dates,
  color,
  height = 48,
  zeroLine = false,
}: {
  values: (number | null)[]
  dates: string[]
  color: string
  height?: number
  zeroLine?: boolean
}) {
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

// 后验堆叠面积图（逐利/观望/避险，带 X 时间轴）
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

// ── 板块状态热力网格 ───────────────────────────────────────────
function SectorGrid({ sectors }: { sectors: SectorRegimePoint[] }) {
  if (sectors.length === 0) {
    return <div className="text-sm text-gray-400 py-6 text-center">暂无板块数据，点右上「重新计算」触发行业级计算</div>
  }
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
      {sectors.map((s) => {
        const lab = s.confirmed_label ?? s.regime_label
        const c = colorOf(lab)
        return (
          <div key={s.sector} className="rounded-xl p-4 flex flex-col gap-1.5 border" style={{ background: `${c}0f`, borderColor: `${c}33` }}>
            <div className="flex items-center justify-between">
              <span className="text-sm font-bold text-gray-800">{s.sector_name}</span>
              <span className="text-xs font-bold px-2 py-0.5 rounded-md" style={{ color: c, background: `${c}1f` }}>
                {labelZh(lab)}
              </span>
            </div>
            <div className="flex items-end justify-between">
              <div className="flex flex-col">
                <span className="text-[10px] text-gray-400 font-semibold">相对大盘</span>
                <span className="text-sm font-bold font-mono tabular-nums" style={{ color: (s.rs_vs_market ?? 0) >= 0 ? LABEL_COLOR.risk_on : LABEL_COLOR.risk_off }}>
                  {s.rs_vs_market === null ? '—' : `${s.rs_vs_market >= 0 ? '+' : ''}${(s.rs_vs_market * 100).toFixed(1)}%`}
                </span>
              </div>
              <div className="flex flex-col items-end">
                <span className="text-[10px] text-gray-400 font-semibold">仓位系数</span>
                <span className="text-lg font-black font-mono tabular-nums text-gray-800">{s.factor_weight === null ? '—' : s.factor_weight.toFixed(2)}</span>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default function RegimePage() {
  const [data, setData] = useState<RegimeResponse | null>(null)
  const [sectors, setSectors] = useState<SectorRegimePoint[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [limit, setLimit] = useState(250)
  const [showAdvanced, setShowAdvanced] = useState(false)

  const load = useCallback(async (lim: number) => {
    setLoading(true)
    setError(null)
    try {
      const resp = await fetchRegime(lim)
      setData(resp)
    } catch {
      setError('加载市场状态失败')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadSectors = useCallback(async () => {
    try {
      const resp = await fetchSectorRegimes()
      setSectors(resp.sectors)
    } catch {
      // 板块数据可选，失败不阻塞主面板
    }
  }, [])

  useEffect(() => {
    load(limit)
  }, [load, limit])

  useEffect(() => {
    loadSectors()
  }, [loadSectors])

  const handleRun = async () => {
    setRunning(true)
    setError(null)
    try {
      await triggerRegimeStage()
      await Promise.all([load(limit), loadSectors()])
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

  // 最近一次状态切换（面板顶部的“发生了什么”）
  let lastSwitch: { date: string; from: string; to: string } | null = null
  if (data) {
    const confirmed = data.history.filter((p) => p.confirmed_label)
    for (let i = confirmed.length - 1; i > 0; i--) {
      if (confirmed[i].confirmed_label !== confirmed[i - 1].confirmed_label) {
        lastSwitch = {
          date: confirmed[i].trade_date,
          from: confirmed[i - 1].confirmed_label!,
          to: confirmed[i].confirmed_label!,
        }
        break
      }
    }
  }

  return (
    <DashboardShell>
      <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
        <div className="max-w-6xl mx-auto space-y-6">
          {/* 顶部标题 + 操作 */}
          <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
            <div className="flex flex-col gap-1.5">
              <h1 className="text-2xl font-extrabold text-gray-900 tracking-tight">市场状态监控</h1>
              <p className="text-sm text-gray-500 max-w-2xl leading-relaxed">
                判断当下市场是<span className="font-semibold text-red-600">逐利</span>、
                <span className="font-semibold text-amber-600">观望</span>还是
                <span className="font-semibold text-green-600">避险</span>，并给出对动量类因子的仓位建议。
              </p>
            </div>
            <button
              onClick={handleRun}
              disabled={running}
              className="px-5 py-2.5 rounded-xl bg-gray-900 text-white text-sm font-bold hover:bg-gray-800 disabled:opacity-50 transition-all whitespace-nowrap self-start"
            >
              {running ? '计算中…' : '重新计算'}
            </button>
          </div>

          {error && (
            <div className="px-4 py-3 rounded-xl bg-red-50 border border-red-100 text-red-600 text-sm font-medium">{error}</div>
          )}

          {loading && !data && (
            <div className="flex items-center justify-center h-[280px]">
              <Spinner size={40} />
            </div>
          )}

          {/* ── Hero：当前状态 ─────────────────────────── */}
          {latest && (
            <div
              className="rounded-3xl p-7 sm:p-8 text-white shadow-lg relative overflow-hidden"
              style={{ background: `linear-gradient(135deg, ${heroColor} 0%, ${heroColor}cc 100%)` }}
            >
              <div className="relative flex flex-col lg:flex-row lg:items-center gap-6">
                <div className="flex-1">
                  <div className="text-xs font-bold uppercase tracking-widest text-white/70 mb-2">当前市场状态</div>
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

          {/* 最近状态切换提示 */}
          {lastSwitch && (
            <div className="flex items-center gap-2 text-sm bg-white rounded-xl border border-gray-100 px-4 py-3 shadow-sm">
              <span className="text-gray-400 font-medium">最近一次状态切换</span>
              <span className="font-mono text-gray-500">{lastSwitch.date}</span>
              <span className="font-bold" style={{ color: colorOf(lastSwitch.from) }}>{labelZh(lastSwitch.from)}</span>
              <span className="text-gray-400">→</span>
              <span className="font-bold" style={{ color: colorOf(lastSwitch.to) }}>{labelZh(lastSwitch.to)}</span>
            </div>
          )}

          {/* ── 信号解读：把数字翻译成结论 ─────────────── */}
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

          {/* ── 板块状态：每个行业单独的 regime ─────────── */}
          {sectors.length > 0 && (
            <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm">
              <div className="flex items-baseline justify-between mb-2 flex-wrap gap-2">
                <h2 className="text-base font-bold text-gray-800">板块状态</h2>
                <span className="text-xs text-gray-400">每个行业单独拟合 HMM，按逐利程度排序 · <span className="text-red-600 font-semibold">红=逐利</span> <span className="text-amber-600 font-semibold">橙=观望</span> <span className="text-green-600 font-semibold">绿=避险</span></span>
              </div>
              <SectorGrid sectors={sectors} />
            </div>
          )}

          {/* 区间选择 */}
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-1.5 bg-gray-100/70 p-1 rounded-xl">
              {RANGE_OPTIONS.map((r) => (
                <button
                  key={r.limit}
                  onClick={() => setLimit(r.limit)}
                  className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${
                    limit === r.limit ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-900'
                  }`}
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>

          {/* 状态后验时间轴 */}
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

          {/* 进阶：原始信号趋势图 */}
          {data && !loading && (
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
              <button
                onClick={() => setShowAdvanced((v) => !v)}
                className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-gray-50 transition-colors"
              >
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
      </div>
    </DashboardShell>
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
