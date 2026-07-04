'use client'

import { useState, useCallback, FormEvent } from 'react'
import {
  fetchInstitutionalSignals,
  type InstitutionalSignalReport,
  type DimensionScore,
  type SignalItem,
} from '@/lib/api/institutional_signals'
import DashboardShell from '@/components/layout/DashboardShell'
import Spinner from '@/components/ui/Spinner'

function getErrorMessage(err: unknown): string {
  const e = err as { response?: { status?: number }; code?: string; message?: string }
  const status = e?.response?.status
  if (status === 422) return '股票代码格式不正确（仅限字母，如 AAPL）'
  if (status === 404) return '数据接口暂不可用（404），请稍后重试'
  if (status && status >= 500) return `服务器错误（${status}），请稍后重试`
  if (e?.code === 'ECONNABORTED') return '请求超时，请稍后重试'
  if (status) return `数据加载失败（${status}）`
  return `数据加载失败：${e?.message ?? '网络错误'}`
}

// 方向 → 箭头与配色
function dirStyle(dir: SignalItem['direction']): { arrow: string; cls: string } {
  if (dir === 'up') return { arrow: '↑', cls: 'text-emerald-600' }
  if (dir === 'down') return { arrow: '↓', cls: 'text-rose-600' }
  return { arrow: '→', cls: 'text-gray-400' }
}

// 综合分 → 配色
function scoreColor(score: number): string {
  if (score >= 70) return 'text-emerald-600'
  if (score >= 55) return 'text-lime-600'
  if (score <= 35) return 'text-rose-600'
  if (score <= 45) return 'text-amber-600'
  return 'text-gray-500'
}

function scoreBarColor(score: number): string {
  if (score >= 70) return 'bg-emerald-500'
  if (score >= 55) return 'bg-lime-500'
  if (score <= 35) return 'bg-rose-500'
  if (score <= 45) return 'bg-amber-500'
  return 'bg-gray-400'
}

function DimensionCard({ dim }: { dim: DimensionScore }) {
  const unavailable = dim.status === 'unavailable'
  return (
    <div
      className={`rounded-2xl border p-5 transition ${
        unavailable ? 'border-gray-100 bg-gray-50/50 opacity-70' : 'border-gray-200 bg-white shadow-sm'
      }`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <div>
          <h3 className="text-base font-bold text-gray-900">{dim.label}</h3>
          <p className="mt-0.5 text-xs text-gray-500">{dim.question}</p>
        </div>
        <span className={`text-2xl font-extrabold tabular-nums ${scoreColor(dim.score)}`}>
          {dim.score.toFixed(0)}
        </span>
      </div>

      {/* 评分条 */}
      <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
        <div className={`h-full rounded-full ${scoreBarColor(dim.score)}`} style={{ width: `${dim.score}%` }} />
      </div>

      {dim.status === 'partial' && (
        <p className="mt-2 text-[11px] font-medium text-amber-600">部分数据缺失，评分仅供参考</p>
      )}
      {unavailable && (
        <p className="mt-2 text-[11px] font-medium text-gray-400">
          {dim.signals[0]?.detail ?? '待接入'}
        </p>
      )}

      {/* 信号明细 */}
      {!unavailable && (
        <ul className="mt-3 space-y-1.5">
          {dim.signals
            .filter((s) => s.value || s.hit)
            .map((s) => {
              const { arrow, cls } = dirStyle(s.direction)
              return (
                <li key={s.key} className="flex items-center justify-between gap-2 text-sm">
                  <span className="text-gray-600">{s.label}</span>
                  <span className={`flex items-center gap-1 font-semibold ${cls}`}>
                    {s.value ?? ''}
                    <span aria-hidden>{arrow}</span>
                    {s.hit && <span className="ml-0.5 h-1.5 w-1.5 rounded-full bg-current" />}
                  </span>
                </li>
              )
            })}
        </ul>
      )}
    </div>
  )
}

export default function InstitutionalSignalsPage() {
  const [symbol, setSymbol] = useState('')
  const [data, setData] = useState<InstitutionalSignalReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback((sym: string) => {
    const clean = sym.trim().toUpperCase()
    if (!clean) return
    setLoading(true)
    setError('')
    fetchInstitutionalSignals(clean)
      .then((res) => setData(res))
      .catch((err) => {
        console.error('[institutional-signals] fetch error:', err?.response?.status, err?.message)
        setError(getErrorMessage(err))
        setData(null)
      })
      .finally(() => setLoading(false))
  }, [])

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    load(symbol)
  }

  return (
    <DashboardShell>
      <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
        {/* 页头 */}
        <div className="flex flex-col gap-1.5">
          <h1 className="text-3xl font-extrabold tracking-tight text-gray-900">机构资金信号</h1>
          <p className="text-sm text-gray-500">
            五维决策链（预期 · 仓位 · 参与度 · 基本面 · 确认），只看状态，不看数据堆砌。
          </p>
        </div>

        {/* 搜索 */}
        <form onSubmit={onSubmit} className="flex gap-2">
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="输入美股代码，如 AAPL / NVDA"
            className="flex-1 rounded-xl border border-gray-300 px-4 py-2.5 text-sm outline-none focus:border-gray-900 focus:ring-1 focus:ring-gray-900"
          />
          <button
            type="submit"
            disabled={loading || !symbol.trim()}
            className="rounded-xl bg-gray-900 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-gray-700 disabled:opacity-40"
          >
            分析
          </button>
        </form>

        {loading && (
          <div className="flex justify-center py-20">
            <Spinner />
          </div>
        )}

        {error && !loading && (
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}

        {data && !loading && (
          <div className="space-y-6">
            {/* 结论横幅 */}
            <div className="rounded-2xl border border-gray-200 bg-gradient-to-br from-gray-50 to-white p-6 shadow-sm">
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <div>
                  <span className="text-xl font-extrabold text-gray-900">{data.symbol}</span>
                  <span className="ml-2 text-sm text-gray-500">{data.name}</span>
                  <span className="ml-2 text-xs text-gray-400">· {data.as_of}</span>
                </div>
                <div className="text-right">
                  <div className={`text-3xl font-extrabold tabular-nums ${scoreColor(data.composite_score)}`}>
                    {data.composite_score.toFixed(0)}
                  </div>
                  <div className="text-[11px] uppercase tracking-wide text-gray-400">综合分</div>
                </div>
              </div>
              <p className="mt-3 text-sm font-medium text-gray-700">{data.headline}</p>

              {/* 状态标签 */}
              <div className="mt-4 flex flex-wrap gap-2">
                {data.states.map((st) => (
                  <div
                    key={st.key}
                    className="group relative rounded-full border border-gray-200 bg-white px-3 py-1.5 text-sm font-semibold text-gray-800 shadow-sm"
                    title={st.meaning}
                  >
                    <span className="mr-1">{st.emoji}</span>
                    {st.label}
                    <span className="ml-1 text-amber-400">{'★'.repeat(st.stars)}</span>
                    {st.evidence.length > 0 && (
                      <span className="ml-2 hidden text-xs font-normal text-gray-500 sm:inline">
                        {st.evidence.join(' · ')}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* 五维卡片 */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {data.dimensions.map((dim) => (
                <DimensionCard key={dim.key} dim={dim} />
              ))}
            </div>

            <p className="text-center text-xs text-gray-400">
              仓位 / 基本面 / 确认维度将在后续版本接入（期权、财报、Insider·13F·ETF Flow）
            </p>
          </div>
        )}

        {!data && !loading && !error && (
          <div className="rounded-2xl border border-dashed border-gray-200 py-20 text-center text-sm text-gray-400">
            输入一个美股代码，查看它的机构资金信号
          </div>
        )}
      </div>
    </DashboardShell>
  )
}
