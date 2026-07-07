'use client'

/* eslint-disable react-hooks/set-state-in-effect */

import { useState, useCallback, useEffect, useRef, FormEvent } from 'react'
import {
  fetchInstitutionalSignals,
  fetchLeaderboard,
  type InstitutionalSignalReport,
  type DimensionScore,
  type SignalItem,
  type LeaderboardEntry,
  type BuyStage,
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

// 迷你价格走势（近 30 日收盘）
function Sparkline({ data }: { data: number[] }) {
  if (!data || data.length < 2) return null
  const w = 140
  const h = 40
  const min = Math.min(...data)
  const max = Math.max(...data)
  const span = max - min || 1
  const pts = data
    .map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / span) * h}`)
    .join(' ')
  const up = data[data.length - 1] >= data[0]
  const stroke = up ? '#059669' : '#e11d48'
  const chgPct = ((data[data.length - 1] - data[0]) / data[0]) * 100
  return (
    <div className="flex items-center gap-2">
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="overflow-visible">
        <polyline points={pts} fill="none" stroke={stroke} strokeWidth="1.5"
          strokeLinejoin="round" strokeLinecap="round" />
      </svg>
      <div className="text-right">
        <div className={`text-sm font-bold tabular-nums ${up ? 'text-emerald-600' : 'text-rose-600'}`}>
          {chgPct >= 0 ? '+' : ''}{chgPct.toFixed(1)}%
        </div>
        <div className="text-[10px] text-gray-400">近 30 日</div>
      </div>
    </div>
  )
}

// 加载骨架屏
function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-2xl border border-gray-200 bg-white p-5">
      <div className="h-4 w-16 rounded bg-gray-200" />
      <div className="mt-2 h-3 w-32 rounded bg-gray-100" />
      <div className="mt-4 h-1.5 w-full rounded-full bg-gray-100" />
      <div className="mt-4 space-y-2">
        <div className="h-3 w-full rounded bg-gray-100" />
        <div className="h-3 w-2/3 rounded bg-gray-100" />
      </div>
    </div>
  )
}

// 买入视角阶梯：把状态按买入价值排成「早 → 晚」，高亮当前所处
function BuyLadder({ headline, ladder }: { headline: string; ladder: BuyStage[] }) {
  if (!ladder || ladder.length === 0) return null
  return (
    <div className="rounded-2xl border border-indigo-100 bg-indigo-50/40 p-5">
      <div className="flex items-center gap-2">
        <span className="text-base">💡</span>
        <h3 className="text-sm font-bold text-gray-900">买入视角</h3>
        <span className="text-[11px] text-gray-400">资金链条：早 → 晚</span>
      </div>
      <p className="mt-1.5 text-sm font-medium text-gray-700">{headline}</p>

      <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-5">
        {ladder.map((r, i) => (
          <div
            key={r.key}
            className={`relative rounded-xl border p-3 transition ${
              r.active
                ? 'border-indigo-300 bg-white shadow-sm ring-1 ring-indigo-200'
                : 'border-gray-100 bg-gray-50/60 opacity-60'
            }`}
          >
            <div className="text-[10px] font-semibold text-gray-400">
              {i === 0 ? '最早' : i === ladder.length - 1 ? '最晚' : `第 ${i + 1} 阶`}
            </div>
            <div className="mt-0.5 flex items-center gap-1 text-sm font-bold text-gray-900">
              <span>{r.emoji}</span>
              <span className={r.active ? '' : 'text-gray-500'}>{r.label}</span>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-1">
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                r.active ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-400'
              }`}>{r.timing}</span>
              <span className="text-[10px] text-gray-400">{r.edge}</span>
            </div>
            {r.active && <p className="mt-1.5 text-[11px] leading-tight text-gray-500">{r.thesis}</p>}
          </div>
        ))}
      </div>
    </div>
  )
}

// 单条信号：可点开查看「原始数据 → 计算式 → 判定规则 → 结论」
function SignalRow({ s }: { s: SignalItem }) {
  const [show, setShow] = useState(false)
  const { arrow, cls } = dirStyle(s.direction)
  const hasExplain = !!s.explain
  return (
    <li className="text-sm">
      <button
        type="button"
        onClick={() => hasExplain && setShow((v) => !v)}
        className={`flex w-full items-start justify-between gap-2 text-left ${hasExplain ? 'cursor-pointer' : 'cursor-default'}`}
      >
        <div className="min-w-0">
          <span className="text-gray-700">{s.label}</span>
          {hasExplain && (
            <span className="ml-1 text-[10px] text-gray-400">{show ? '收起' : '为什么？'}</span>
          )}
          {s.detail && <p className="text-[11px] leading-tight text-gray-400">{s.detail}</p>}
        </div>
        <span className={`flex shrink-0 items-center gap-1 font-semibold ${cls}`}>
          {s.value ?? ''}
          <span aria-hidden>{arrow}</span>
          {s.hit && <span className="ml-0.5 h-1.5 w-1.5 rounded-full bg-current" />}
        </span>
      </button>

      {show && s.explain && (
        <div className="mt-2 space-y-1.5 rounded-lg bg-gray-50 p-3 text-[11px] leading-relaxed text-gray-600">
          {s.explain.inputs.length > 0 && (
            <div>
              <span className="font-semibold text-gray-500">原始数据</span>
              <ul className="mt-0.5 list-disc pl-4">
                {s.explain.inputs.map((x, i) => <li key={i}>{x}</li>)}
              </ul>
            </div>
          )}
          {s.explain.formula && (
            <div><span className="font-semibold text-gray-500">计算式　</span><span className="font-mono">{s.explain.formula}</span></div>
          )}
          {s.explain.thresholds && (
            <div><span className="font-semibold text-gray-500">判定规则</span> {s.explain.thresholds}</div>
          )}
          {s.explain.conclusion && (
            <div className="text-gray-800"><span className="font-semibold text-gray-500">结论　　</span>{s.explain.conclusion}</div>
          )}
          {s.explain.source && (
            <div className="text-[10px] text-gray-400">数据来源：{s.explain.source}</div>
          )}
        </div>
      )}
    </li>
  )
}

function DimensionCard({ dim }: { dim: DimensionScore }) {
  const unavailable = dim.status === 'unavailable'
  const detailSignals = dim.signals.filter((s) => s.value || s.hit)
  const [open, setOpen] = useState(true)
  return (
    <div
      className={`rounded-2xl border p-5 transition ${
        unavailable ? 'border-gray-100 bg-gray-50/50 opacity-70' : 'border-gray-200 bg-white shadow-sm'
      }`}
    >
      <button
        type="button"
        onClick={() => !unavailable && detailSignals.length > 0 && setOpen((v) => !v)}
        className="flex w-full items-baseline justify-between gap-2 text-left"
      >
        <div>
          <h3 className="text-base font-bold text-gray-900">{dim.label}</h3>
          <p className="mt-0.5 text-xs text-gray-500">{dim.question}</p>
        </div>
        <div className="flex items-center gap-1.5">
          <span className={`text-2xl font-extrabold tabular-nums ${scoreColor(dim.score)}`}>
            {dim.score.toFixed(0)}
          </span>
          {!unavailable && detailSignals.length > 0 && (
            <span className={`text-gray-300 transition ${open ? 'rotate-90' : ''}`} aria-hidden>›</span>
          )}
        </div>
      </button>

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

      {/* 信号明细：每条可点开看完整推导 */}
      {!unavailable && open && (
        <ul className="mt-3 space-y-2.5">
          {detailSignals.map((s) => <SignalRow key={s.key} s={s} />)}
        </ul>
      )}
    </div>
  )
}

// 榜单状态筛选（按买入价值早→晚排序：聪明钱最早/最稀有）
// 标签须与状态卡/买入视角阶梯（STATE_LABELS）一致，避免「外面简称、里面全称」不一致
const STATE_FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'smart_money', label: '💰 聪明钱' },
  { key: 'institution_accumulation', label: '🔥 机构建仓' },
  { key: 'fundamental_turn', label: '🌱 基本面改善' },
  { key: 'expectation_upgrade', label: '📈 预期上修' },
  { key: 'breakout_confirmation', label: '🚀 趋势确认' },
] as const

// 五维中文标签（与 DIMENSION_META 对齐），用于排序按钮与榜单右列
const DIMENSION_LABELS: Record<string, string> = {
  expectation: '预期',
  positioning: '仓位',
  participation: '参与度',
  fundamental: '基本面',
  confirmation: '确认',
}

// 榜单排序维度：综合分（默认，保留后端「偏多优先」排序）+ 五维分
const SORT_OPTIONS = [
  { key: 'composite', label: '综合分' },
  ...Object.entries(DIMENSION_LABELS).map(([key, label]) => ({ key, label })),
] as const

function LeaderboardBoard(
  { board, onPick, activeFilter = 'all', sortKey = 'composite' }:
  { board: LeaderboardEntry[]; onPick: (s: string) => void; activeFilter?: string; sortKey?: string },
) {
  const byDimension = sortKey !== 'composite'
  return (
    <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
      {board.map((e, i) => {
        // 筛选某状态时，行上就显示那个状态（否则只显示 top_state，会看不到筛选命中的状态）
        const shown = (activeFilter !== 'all' && e.states.find((s) => s.key === activeFilter)) || e.top_state
        return (
        <button
          key={e.symbol}
          onClick={() => onPick(e.symbol)}
          className="flex w-full items-center gap-3 border-b border-gray-100 px-4 py-3 text-left transition last:border-0 hover:bg-gray-50"
        >
          <span className="w-5 shrink-0 text-center text-sm font-bold text-gray-400">{i + 1}</span>
          {/* 名称 + 状态：窄屏纵向堆叠，宽屏并排 */}
          <div className="flex min-w-0 flex-1 flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
            <div className="min-w-0 sm:w-40 sm:shrink-0">
              <div className="text-sm font-bold text-gray-900">{e.symbol}</div>
              <div className="truncate text-xs text-gray-400">{e.name}</div>
            </div>
            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
              {shown ? (
                <>
                  <span className="inline-flex max-w-full items-center gap-1 whitespace-nowrap rounded-full bg-gray-100 px-2.5 py-1 text-xs font-semibold text-gray-800">
                    <span>{shown.emoji}</span>
                    <span className="truncate">{shown.label}</span>
                    <span className="text-amber-400">{'★'.repeat(shown.stars)}</span>
                  </span>
                  {shown.buy_timing && (
                    <span className="whitespace-nowrap text-[10px] text-gray-400">
                      {shown.buy_timing} · {shown.buy_edge}
                    </span>
                  )}
                </>
              ) : (
                <span className="text-xs text-gray-400">无显著偏多状态</span>
              )}
            </div>
          </div>
          <div className="w-20 shrink-0 text-right">
            {byDimension ? (() => {
              const dv = e.dimension_scores[sortKey]
              return (
                <>
                  <div className={`text-lg font-extrabold tabular-nums ${dv == null ? 'text-gray-300' : scoreColor(dv)}`}>
                    {dv == null ? '—' : dv.toFixed(0)}
                  </div>
                  <div className="text-[10px] text-gray-400">
                    {DIMENSION_LABELS[sortKey]} · 综合 {e.composite_score.toFixed(0)}
                  </div>
                </>
              )
            })() : (
              <>
                <div className={`text-lg font-extrabold tabular-nums ${scoreColor(e.composite_score)}`}>
                  {e.composite_score.toFixed(0)}
                </div>
                <div className="text-[10px] text-gray-400">{e.coverage}/5 · {e.confidence}</div>
              </>
            )}
          </div>
        </button>
        )
      })}
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
  const [boardSource, setBoardSource] = useState('')
  const [boardLoading, setBoardLoading] = useState(true)
  const [boardComputing, setBoardComputing] = useState(false)
  const [boardNote, setBoardNote] = useState('')
  const [boardFilter, setBoardFilter] = useState<string>('all')
  const [boardSort, setBoardSort] = useState<string>('composite')
  const [universe, setUniverse] = useState<'sp500' | 'nasdaq100'>('sp500')
  const [detailTab, setDetailTab] = useState<'signals' | 'research'>('signals')

  const load = useCallback((sym: string) => {
    const clean = sym.trim().toUpperCase()
    if (!clean) return
    setSymbol(clean)
    setDetailTab('signals')
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

  // 轮询代际：每次重新开轮询自增，旧轮询回调据此自行作废（切换 universe / 手动刷新）
  const pollGen = useRef(0)
  const pollTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const startBoardPoll = useCallback((force: boolean) => {
    clearTimeout(pollTimer.current)
    const gen = ++pollGen.current
    setBoardLoading(true)
    setBoardComputing(force) // 强制刷新时立刻进入「扫描中」态，避免闪回旧榜
    setBoard(null)
    setBoardNote('')
    const poll = (refresh: boolean) => {
      fetchLeaderboard(universe, refresh)
        .then((res) => {
          if (gen !== pollGen.current) return // 已被更晚的轮询取代
          if (res.status === 'computing') {
            setBoardComputing(true)
            pollTimer.current = setTimeout(() => poll(false), 15000) // 扫描中，15s 后重试
          } else {
            setBoardComputing(false)
            setBoard(res.entries)
            setBoardAsOf(res.as_of)
            setBoardSource(res.universe_source)
            // 数据源整体不可用时携带原因，供空态展示（区别于「今日无热门」）
            setBoardNote(res.status === 'unavailable' ? res.note : '')
            setBoardLoading(false)
          }
        })
        .catch((err) => {
          console.error('[leaderboard] fetch error:', err?.response?.status, err?.message)
          if (gen === pollGen.current) setBoardLoading(false)
        })
    }
    poll(force)
  }, [universe])

  useEffect(() => {
    startBoardPoll(false)
    return () => { pollGen.current++; clearTimeout(pollTimer.current) }
  }, [startBoardPoll])

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
          <div className="space-y-6">
            <div className="h-28 animate-pulse rounded-2xl bg-gray-100" />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {[0, 1, 2, 3, 4].map((i) => <SkeletonCard key={i} />)}
            </div>
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

            <div className="inline-flex rounded-xl border border-gray-200 bg-white p-1">
              {[
                { id: 'signals', label: '机构信号' },
                { id: 'research', label: '企业研究' },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setDetailTab(tab.id as 'signals' | 'research')}
                  className={`h-9 rounded-lg px-3 text-sm font-semibold transition ${
                    detailTab === tab.id ? 'bg-gray-900 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {detailTab === 'research' ? (
              <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
                <iframe
                  src={`/company-research?symbol=${encodeURIComponent(data.symbol)}&embedded=1`}
                  title={`${data.symbol} 企业研究`}
                  className="h-[78vh] w-full border-0"
                />
              </div>
            ) : (
              <>
            {/* 结论横幅 */}
            <div className="rounded-2xl border border-gray-200 bg-gradient-to-br from-gray-50 to-white p-6 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div>
                    <span className="text-xl font-extrabold text-gray-900">{data.symbol}</span>
                    <span className="ml-2 text-sm text-gray-500">{data.name}</span>
                    <span className="ml-2 text-xs text-gray-400">· {data.as_of}</span>
                  </div>
                  {data.price_history?.length > 1 && (
                    <div className="mt-2"><Sparkline data={data.price_history} /></div>
                  )}
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
                  {/* 分数锚点 */}
                  <div className="mt-1 text-[10px] text-gray-400">≥70 强 · 55–70 偏多 · &lt;45 偏空</div>
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
                    {st.logic && (
                      <p className="mt-1 text-[11px] text-gray-400">
                        <span className="font-semibold text-gray-500">触发逻辑：</span>{st.logic}
                      </p>
                    )}
                    {st.evidence.length > 0 && (
                      <p className="mt-1 text-[11px] text-gray-400">
                        <span className="font-semibold text-gray-500">已命中：</span>{st.evidence.join(' · ')}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* 买入视角阶梯 */}
            <BuyLadder headline={data.buy_headline} ladder={data.buy_ladder} />

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
              </>
            )}
          </div>
        )}

        {!data && !loading && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-lg font-bold text-gray-900">🔥 今日机构建仓榜</h2>
              <div className="flex items-center gap-2">
                {boardAsOf && (
                  <span className="text-xs text-gray-400">
                    {boardAsOf} · 点击查看完整五维
                    {boardSource.includes('fallback') && (
                      <span className="ml-1 text-amber-500">· 成分股动态获取失败，当前为兜底名单</span>
                    )}
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => startBoardPoll(true)}
                  disabled={boardComputing}
                  title="清空缓存并重新扫描当前 universe"
                  className="inline-flex items-center gap-1 rounded-lg border border-gray-200 bg-white px-2.5 py-1 text-xs font-semibold text-gray-600 transition hover:bg-gray-50 disabled:opacity-40"
                >
                  <span aria-hidden className={boardComputing ? 'animate-spin' : ''}>↻</span>
                  {boardComputing ? '重扫中…' : '刷新'}
                </button>
              </div>
            </div>

            {/* universe 切换：标普 500 / 纳指 100（QQQ）*/}
            <div className="inline-flex rounded-xl border border-gray-200 bg-gray-50 p-0.5">
              {([['sp500', '标普 500'], ['nasdaq100', '纳指 100 · QQQ']] as const).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setUniverse(key)}
                  className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold transition ${
                    universe === key ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-800'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            {boardComputing && (
              <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-gray-200 py-16 text-center">
                <Spinner />
                <p className="text-sm text-gray-500">
                  首次扫描{universe === 'nasdaq100' ? '纳指 100' : '标普 500'}成分股中，约需 1–2 分钟，页面会自动刷新…
                </p>
              </div>
            )}
            {!boardComputing && boardLoading && (
              <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white">
                {[0, 1, 2, 3, 4, 5].map((i) => (
                  <div key={i} className="flex items-center gap-3 border-b border-gray-100 px-4 py-3.5 last:border-0">
                    <div className="h-8 w-8 animate-pulse rounded bg-gray-100" />
                    <div className="flex-1 space-y-1.5">
                      <div className="h-3 w-24 animate-pulse rounded bg-gray-200" />
                      <div className="h-2.5 w-40 animate-pulse rounded bg-gray-100" />
                    </div>
                    <div className="h-6 w-10 animate-pulse rounded bg-gray-100" />
                  </div>
                ))}
              </div>
            )}
            {!boardComputing && !boardLoading && board && board.length > 0 && (() => {
              // 计数/筛选按「任一命中状态」，而非仅 top_state——否则 4★ 的趋势确认
              // 总被同票的 5★ 状态盖住，导致筛选几乎为空。
              const has = (e: LeaderboardEntry, key: string) => e.states.some((s) => s.key === key)
              const counts: Record<string, number> = { all: board.length }
              STATE_FILTERS.forEach((f) => {
                if (f.key !== 'all') counts[f.key] = board.filter((e) => has(e, f.key)).length
              })
              const filtered = boardFilter === 'all'
                ? board
                : board.filter((e) => has(e, boardFilter))
              // 排序：综合分保留后端「偏多优先」原序；按维度时降序，缺失该维度的沉底
              const sorted = boardSort === 'composite'
                ? filtered
                : [...filtered].sort((a, b) => {
                    const av = a.dimension_scores[boardSort]
                    const bv = b.dimension_scores[boardSort]
                    if (av == null && bv == null) return 0
                    if (av == null) return 1
                    if (bv == null) return -1
                    return bv - av
                  })
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
                  {/* 排序维度：综合分（默认）+ 五维 */}
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-medium text-gray-400">排序</span>
                    {SORT_OPTIONS.map((o) => (
                      <button
                        key={o.key}
                        onClick={() => setBoardSort(o.key)}
                        className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                          boardSort === o.key
                            ? 'bg-indigo-600 text-white'
                            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                        }`}
                      >
                        {o.label}
                      </button>
                    ))}
                  </div>
                  {sorted.length > 0 ? (
                    <LeaderboardBoard board={sorted} onPick={load} activeFilter={boardFilter} sortKey={boardSort} />
                  ) : (
                    <div className="rounded-2xl border border-dashed border-gray-200 py-12 text-center text-sm text-gray-400">
                      当前筛选下暂无标的
                    </div>
                  )}
                </>
              )
            })()}
            {!boardComputing && !boardLoading && (!board || board.length === 0) && (
              <div className="rounded-2xl border border-dashed border-gray-200 py-16 text-center text-sm text-gray-400 px-6">
                {boardNote ? (
                  <>
                    <div className="text-gray-500 font-medium mb-1">机构建仓榜暂不可用</div>
                    <div className="max-w-xl mx-auto leading-relaxed">{boardNote}</div>
                  </>
                ) : (
                  '榜单暂不可用，可直接在上方输入代码查询'
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </DashboardShell>
  )
}
