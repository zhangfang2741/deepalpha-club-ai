'use client'

import { useState, useCallback, useEffect, FormEvent } from 'react'
import {
  fetchInstitutionalSignals,
  fetchLeaderboard,
  type InstitutionalSignalReport,
  type DimensionScore,
  type SignalItem,
  type LeaderboardEntry,
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

// 置信度徽章配色（由数据覆盖度决定）
function confidenceStyle(conf: string): string {
  if (conf === '高') return 'bg-emerald-100 text-emerald-700'
  if (conf === '中') return 'bg-amber-100 text-amber-700'
  return 'bg-gray-200 text-gray-600'
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

      {/* 信号明细（含后端计算口径，直接可解释）*/}
      {!unavailable && (
        <ul className="mt-3 space-y-2">
          {dim.signals
            .filter((s) => s.value || s.hit)
            .map((s) => {
              const { arrow, cls } = dirStyle(s.direction)
              return (
                <li key={s.key} className="flex items-start justify-between gap-2 text-sm">
                  <div className="min-w-0">
                    <span className="text-gray-700">{s.label}</span>
                    {s.detail && (
                      <p className="text-[11px] leading-tight text-gray-400">{s.detail}</p>
                    )}
                  </div>
                  <span className={`flex shrink-0 items-center gap-1 font-semibold ${cls}`}>
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

// 榜单状态筛选
const STATE_FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'institution_accumulation', label: '🔥 建仓' },
  { key: 'fundamental_turn', label: '🌱 基本面' },
  { key: 'expectation_upgrade', label: '📈 预期' },
  { key: 'breakout_confirmation', label: '🚀 趋势' },
] as const

function LeaderboardBoard({ board, onPick }: { board: LeaderboardEntry[]; onPick: (s: string) => void }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
      {board.map((e, i) => (
        <button
          key={e.symbol}
          onClick={() => onPick(e.symbol)}
          className="flex w-full items-center gap-3 border-b border-gray-100 px-4 py-3 text-left transition last:border-0 hover:bg-gray-50"
        >
          <span className="w-6 shrink-0 text-center text-sm font-bold text-gray-400">{i + 1}</span>
          <div className="w-32 shrink-0">
            <div className="text-sm font-bold text-gray-900">{e.symbol}</div>
            <div className="truncate text-xs text-gray-400">{e.name}</div>
          </div>
          <div className="flex-1">
            {e.top_state ? (
              <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-semibold text-gray-800">
                {e.top_state.emoji} {e.top_state.label}
                <span className="ml-1 text-amber-400">{'★'.repeat(e.top_state.stars)}</span>
              </span>
            ) : (
              <span className="text-xs text-gray-400">无显著偏多状态</span>
            )}
          </div>
          <div className="w-16 shrink-0 text-right">
            <div className={`text-lg font-extrabold tabular-nums ${scoreColor(e.composite_score)}`}>
              {e.composite_score.toFixed(0)}
            </div>
            <div className="text-[10px] text-gray-400">{e.coverage}/5 · {e.confidence}</div>
          </div>
        </button>
      ))}
    </div>
  )
}

export default function InstitutionalSignalsPage() {
  const [symbol, setSymbol] = useState('')
  const [data, setData] = useState<InstitutionalSignalReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [board, setBoard] = useState<LeaderboardEntry[] | null>(null)
  const [boardAsOf, setBoardAsOf] = useState('')
  const [boardLoading, setBoardLoading] = useState(true)
  const [boardComputing, setBoardComputing] = useState(false)
  const [boardFilter, setBoardFilter] = useState<string>('all')

  const load = useCallback((sym: string) => {
    const clean = sym.trim().toUpperCase()
    if (!clean) return
    setSymbol(clean)
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

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>
    let cancelled = false
    const poll = () => {
      fetchLeaderboard()
        .then((res) => {
          if (cancelled) return
          if (res.status === 'computing') {
            setBoardComputing(true)
            timer = setTimeout(poll, 15000) // 后台扫描中，15s 后重试
          } else {
            setBoardComputing(false)
            setBoard(res.entries)
            setBoardAsOf(res.as_of)
            setBoardLoading(false)
          }
        })
        .catch((err) => {
          console.error('[leaderboard] fetch error:', err?.response?.status, err?.message)
          if (!cancelled) setBoardLoading(false)
        })
    }
    poll()
    return () => { cancelled = true; clearTimeout(timer) }
  }, [])

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    load(symbol)
  }

  const backToBoard = () => { setData(null); setError(''); setSymbol('') }

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
            <button onClick={backToBoard} className="text-sm text-gray-500 transition hover:text-gray-900">
              ← 返回机构建仓榜
            </button>
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
                  <div className="mt-1 flex items-center justify-end gap-1.5">
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${confidenceStyle(data.confidence)}`}>
                      置信度 {data.confidence}
                    </span>
                    <span className="text-[11px] text-gray-400">
                      {data.coverage}/{data.coverage_total} 维
                    </span>
                  </div>
                </div>
              </div>
              <p className="mt-3 text-sm font-medium text-gray-700">{data.headline}</p>

              {/* 状态卡片：含义与证据始终可见（含移动端）*/}
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {data.states.map((st) => (
                  <div key={st.key} className="rounded-xl border border-gray-200 bg-white px-3.5 py-2.5 shadow-sm">
                    <div className="flex items-center gap-1.5 text-sm font-bold text-gray-900">
                      <span>{st.emoji}</span>
                      <span>{st.label}</span>
                      <span className="text-amber-400">{'★'.repeat(st.stars)}</span>
                    </div>
                    <p className="mt-0.5 text-xs text-gray-500">{st.meaning}</p>
                    {st.evidence.length > 0 && (
                      <p className="mt-1 text-[11px] text-gray-400">证据：{st.evidence.join(' · ')}</p>
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
              五维已全部接入。仓位 OI 变化率 / IV Rank、预期 EPS 修正已接入每日快照库（需累积历史后生效）；
              待后续：指引方向（Transcript NLP）、13F（FMP Ultimate 版）、ETF 资金流
            </p>
          </div>
        )}

        {!data && !loading && (
          <div className="space-y-3">
            <div className="flex items-baseline justify-between">
              <h2 className="text-lg font-bold text-gray-900">🔥 今日机构建仓榜</h2>
              {boardAsOf && <span className="text-xs text-gray-400">{boardAsOf} · 点击查看完整五维</span>}
            </div>
            {boardComputing && (
              <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-gray-200 py-16 text-center">
                <Spinner />
                <p className="text-sm text-gray-500">首次扫描 S&P 500 成分股中，约需 1–2 分钟，页面会自动刷新…</p>
              </div>
            )}
            {!boardComputing && boardLoading && (
              <div className="flex justify-center py-16"><Spinner /></div>
            )}
            {!boardComputing && !boardLoading && board && board.length > 0 && (() => {
              const counts: Record<string, number> = { all: board.length }
              board.forEach((e) => { if (e.top_state) counts[e.top_state.key] = (counts[e.top_state.key] ?? 0) + 1 })
              const filtered = boardFilter === 'all'
                ? board
                : board.filter((e) => e.top_state?.key === boardFilter)
              return (
                <>
                  <div className="flex flex-wrap gap-2">
                    {STATE_FILTERS.map((f) => (
                      <button
                        key={f.key}
                        onClick={() => setBoardFilter(f.key)}
                        className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                          boardFilter === f.key
                            ? 'bg-gray-900 text-white'
                            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                        }`}
                      >
                        {f.label}
                        <span className="ml-1 opacity-60">{counts[f.key] ?? 0}</span>
                      </button>
                    ))}
                  </div>
                  {filtered.length > 0 ? (
                    <LeaderboardBoard board={filtered} onPick={load} />
                  ) : (
                    <div className="rounded-2xl border border-dashed border-gray-200 py-12 text-center text-sm text-gray-400">
                      当前筛选下暂无标的
                    </div>
                  )}
                </>
              )
            })()}
            {!boardComputing && !boardLoading && (!board || board.length === 0) && (
              <div className="rounded-2xl border border-dashed border-gray-200 py-16 text-center text-sm text-gray-400">
                榜单暂不可用，可直接在上方输入代码查询
              </div>
            )}
          </div>
        )}
      </div>
    </DashboardShell>
  )
}
