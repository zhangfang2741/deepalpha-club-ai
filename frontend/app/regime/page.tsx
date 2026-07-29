'use client'

import { useEffect, useState, useCallback } from 'react'
import DashboardShell from '@/components/layout/DashboardShell'
import Spinner from '@/components/ui/Spinner'
import {
  fetchRegime,
  triggerRegimeStage,
  REGIME_LABEL_ZH,
  type RegimePoint,
  type RegimeResponse,
} from '@/lib/api/regime'

const RANGE_OPTIONS = [
  { label: '3个月', limit: 90 },
  { label: '6个月', limit: 180 },
  { label: '1年', limit: 250 },
  { label: '2年', limit: 500 },
]

// 状态配色
const LABEL_COLOR: Record<string, string> = {
  risk_on: '#16a34a', // 逐利 绿
  neutral: '#f59e0b', // 观望 橙
  risk_off: '#dc2626', // 避险 红
}

function labelZh(label: string | null): string {
  if (!label) return '数据不足'
  return REGIME_LABEL_ZH[label] ?? label
}

// ── 内联 SVG 折线图 ──────────────────────────────────────────────
function Sparkline({
  values,
  color,
  height = 48,
  zeroLine = false,
}: {
  values: (number | null)[]
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
  return (
    <svg viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" className="w-full" style={{ height }}>
      {zeroY !== null && (
        <line x1={0} y1={zeroY} x2={w} y2={zeroY} stroke="#cbd5e1" strokeWidth={0.5} strokeDasharray="2 2" />
      )}
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

// 后验堆叠面积图（逐利/观望/避险）
function PosteriorStack({ history }: { history: RegimePoint[] }) {
  const rows = history.filter((p) => p.p_risk_off !== null)
  if (rows.length < 2) {
    return <div className="text-sm text-gray-400 py-8 text-center">历史不足，尚无后验（需≥1年历史拟合 HMM）</div>
  }
  const w = 100
  const h = 120
  const n = rows.length
  // 每天从下往上堆叠 risk_off / neutral / risk_on
  const buildArea = (getBottom: (p: RegimePoint) => number, getTop: (p: RegimePoint) => number) => {
    const top = rows.map((p, i) => `${(i / (n - 1)) * w},${h - getTop(p) * h}`)
    const bottom = rows
      .map((p, i) => `${(i / (n - 1)) * w},${h - getBottom(p) * h}`)
      .reverse()
    return `M ${top.join(' L ')} L ${bottom.join(' L ')} Z`
  }
  const off = (p: RegimePoint) => p.p_risk_off ?? 0
  const neu = (p: RegimePoint) => (p.p_risk_off ?? 0) + (p.p_neutral ?? 0)
  const on = () => 1
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="w-full" style={{ height: 160 }}>
      <path d={buildArea(() => 0, off)} fill={LABEL_COLOR.risk_off} opacity={0.85} />
      <path d={buildArea(off, neu)} fill={LABEL_COLOR.neutral} opacity={0.85} />
      <path d={buildArea(neu, on)} fill={LABEL_COLOR.risk_on} opacity={0.85} />
    </svg>
  )
}

function ProbBar({ label, value, color }: { label: string; value: number | null; color: string }) {
  const pct = value === null ? 0 : Math.round(value * 100)
  return (
    <div className="flex items-center gap-3">
      <span className="w-12 text-sm font-semibold text-gray-600">{label}</span>
      <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="w-10 text-right text-sm font-bold text-gray-700">{pct}%</span>
    </div>
  )
}

export default function RegimePage() {
  const [data, setData] = useState<RegimeResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [limit, setLimit] = useState(250)

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
  const latestColor = latest ? LABEL_COLOR[latest.confirmed_label ?? latest.regime_label ?? 'neutral'] ?? '#6b7280' : '#6b7280'

  return (
    <DashboardShell>
      <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
        <div className="max-w-7xl mx-auto space-y-8">
          {/* Header */}
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
            <div className="flex flex-col gap-2">
              <h1 className="text-3xl font-extrabold text-gray-900 tracking-tight">市场状态监控</h1>
              <p className="text-gray-500 max-w-2xl leading-relaxed font-medium">
                资金逐利/避险的三篮子信号（ODS/CF）+ 真拟合 HMM 状态后验。日频「算一次，双消费」：既看面板，又把
                <span className="font-semibold text-gray-700"> p_避险 </span>写入因子表供下游动态加权。
              </p>
            </div>
            <button
              onClick={handleRun}
              disabled={running}
              className="px-5 py-2.5 rounded-xl bg-blue-600 text-white text-sm font-bold hover:bg-blue-700 disabled:opacity-50 transition-all shadow-lg shadow-blue-200 whitespace-nowrap"
            >
              {running ? '计算中…' : '重新计算'}
            </button>
          </div>

          {error && (
            <div className="px-4 py-3 rounded-xl bg-red-50 border border-red-100 text-red-600 text-sm font-medium">
              {error}
            </div>
          )}

          {/* 当前状态 Hero */}
          {latest && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="bg-white rounded-2xl border border-gray-100 p-6 flex flex-col gap-3 shadow-sm">
                <div className="text-xs text-gray-500 font-semibold uppercase tracking-wider">当前状态</div>
                <div className="text-4xl font-extrabold tracking-tight" style={{ color: latestColor }}>
                  {labelZh(latest.confirmed_label ?? latest.regime_label)}
                </div>
                <div className="text-xs text-gray-400 font-medium">
                  {latest.trade_date}
                  {latest.confirmed_label ? '（已确认）' : latest.regime_label ? '（未确认，未满持续天数）' : ''}
                </div>
                <div className="mt-2 flex flex-col gap-2">
                  <ProbBar label="逐利" value={latest.p_risk_on} color={LABEL_COLOR.risk_on} />
                  <ProbBar label="观望" value={latest.p_neutral} color={LABEL_COLOR.neutral} />
                  <ProbBar label="避险" value={latest.p_risk_off} color={LABEL_COLOR.risk_off} />
                </div>
              </div>

              <div className="bg-white rounded-2xl border border-gray-100 p-6 flex flex-col gap-2 shadow-sm">
                <div className="text-xs text-gray-500 font-semibold uppercase tracking-wider">下游因子权重</div>
                <div className="text-4xl font-extrabold text-blue-600 tracking-tight">
                  {latest.factor_weight === null ? '—' : latest.factor_weight.toFixed(2)}
                </div>
                <div className="text-xs text-gray-400 font-medium">= 1 − p_避险（如 动量权重 × 此值）</div>
                <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                  <Metric label="ODS" value={latest.ods} />
                  <Metric label="CF" value={latest.cf} />
                  <Metric label="VIX" value={latest.vix} digits={1} />
                  <Metric label="已实现波动" value={latest.realized_vol} pct />
                </div>
              </div>

              <div className="bg-white rounded-2xl border border-gray-100 p-6 flex flex-col gap-2 shadow-sm">
                <div className="text-xs text-gray-500 font-semibold uppercase tracking-wider">量价确认</div>
                <div className="mt-1 grid grid-cols-2 gap-3 text-sm">
                  <Metric label="OBV 斜率" value={latest.obv_slope} digits={3} />
                  <Metric label="CMF" value={latest.cmf} digits={3} />
                  <Metric label="纳指收益" value={latest.qqq_return} pct />
                </div>
                <div className="text-xs text-gray-400 font-medium mt-2">
                  参数版本：{latest.params_version ?? '—'}（月末冻结重估）
                </div>
              </div>
            </div>
          )}

          {/* 区间选择 */}
          <div className="flex items-center gap-2 bg-gray-100/50 p-1 rounded-xl w-fit">
            {RANGE_OPTIONS.map((r) => (
              <button
                key={r.limit}
                onClick={() => setLimit(r.limit)}
                className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${
                  limit === r.limit ? 'bg-blue-600 text-white shadow' : 'text-gray-500 hover:text-gray-900 hover:bg-white'
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>

          {loading && (
            <div className="flex items-center justify-center h-[200px]">
              <Spinner size={40} />
            </div>
          )}

          {data && !loading && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm lg:col-span-2">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-bold text-gray-700">状态后验（堆叠）</h3>
                  <div className="flex items-center gap-3 text-xs font-semibold">
                    <Legend color={LABEL_COLOR.risk_on} text="逐利" />
                    <Legend color={LABEL_COLOR.neutral} text="观望" />
                    <Legend color={LABEL_COLOR.risk_off} text="避险" />
                  </div>
                </div>
                <PosteriorStack history={data.history} />
              </div>

              <ChartCard title="ODS（进攻−防御）" color="#7c3aed">
                <Sparkline values={data.history.map((p) => p.ods)} color="#7c3aed" zeroLine />
              </ChartCard>
              <ChartCard title="CF（现金−风险资产）" color="#0891b2">
                <Sparkline values={data.history.map((p) => p.cf)} color="#0891b2" zeroLine />
              </ChartCard>
              <ChartCard title="VIX" color="#dc2626">
                <Sparkline values={data.history.map((p) => p.vix)} color="#dc2626" />
              </ChartCard>
              <ChartCard title="CMF（量价）" color="#16a34a">
                <Sparkline values={data.history.map((p) => p.cmf)} color="#16a34a" zeroLine />
              </ChartCard>
            </div>
          )}
        </div>
      </div>
    </DashboardShell>
  )
}

function Metric({ label, value, pct, digits = 2 }: { label: string; value: number | null; pct?: boolean; digits?: number }) {
  const text = value === null ? '—' : pct ? `${(value * 100).toFixed(1)}%` : value.toFixed(digits)
  return (
    <div className="flex flex-col">
      <span className="text-xs text-gray-400 font-semibold">{label}</span>
      <span className="text-lg font-bold text-gray-800">{text}</span>
    </div>
  )
}

function ChartCard({ title, color, children }: { title: string; color: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm">
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
