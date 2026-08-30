'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, Clock, Gavel, Loader2, RefreshCcw } from 'lucide-react'
import DashboardShell from '@/components/layout/DashboardShell'
import { getApiErrorMessage } from '@/lib/api/client'
import { listRuns, type RunSummary } from '@/lib/api/trading_desk'

const STATUS_LABEL: Record<RunSummary['status'], { label: string; tone: string }> = {
  running: { label: '运行中', tone: 'bg-blue-50 text-blue-700 border-blue-200' },
  completed: { label: '已完成', tone: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  cancelled: { label: '已取消', tone: 'bg-gray-100 text-gray-600 border-gray-200' },
  failed: { label: '失败', tone: 'bg-red-50 text-red-700 border-red-200' },
  interrupted: { label: '中断', tone: 'bg-amber-50 text-amber-700 border-amber-200' },
}

function formatDuration(ms: number): string {
  if (!ms || ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  const m = Math.floor(ms / 60_000)
  const s = Math.floor((ms % 60_000) / 1000)
  return `${m}m${s}s`
}

function formatTimestamp(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN', { hour12: false })
}

function VerdictBadge({ signal, confidence }: { signal: RunSummary['verdict_signal']; confidence: RunSummary['verdict_confidence'] }) {
  if (!signal) return <span className="text-xs text-gray-400">未出裁决</span>
  const tone =
    signal === 'BUY' ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
    : signal === 'SELL' ? 'bg-red-50 text-red-700 border-red-200'
    : 'bg-gray-100 text-gray-600 border-gray-200'
  const pct = confidence != null ? Math.round(confidence * 100) : null
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium ${tone}`}>
      <span>{signal}</span>
      {pct !== null && <span className="font-mono text-[11px] opacity-70">{pct}%</span>}
    </span>
  )
}

export default function TradingDeskHistoryPage() {
  const [ticker, setTicker] = useState('')
  const [appliedTicker, setAppliedTicker] = useState('')
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchRuns = useCallback(async (filterTicker: string) => {
    setLoading(true)
    setError(null)
    try {
      const resp = await listRuns({ ticker: filterTicker || undefined, limit: 50 })
      setRuns(resp.runs)
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 数据获取模式：mount 后拉一次
    void fetchRuns('')
  }, [fetchRuns])

  const onSearch = useCallback(() => {
    const next = ticker.trim().toUpperCase()
    setAppliedTicker(next)
    void fetchRuns(next)
  }, [ticker, fetchRuns])

  return (
    <DashboardShell>
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Link
            href="/trading-desk"
            className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-600 hover:bg-gray-50"
          >
            <ArrowLeft className="h-4 w-4" />
            返回交易台
          </Link>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-gray-900">
            <Gavel className="h-6 w-6 text-blue-600" />
            历史运行
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onSearch()
            }}
            placeholder="按标的过滤（如 NVDA）"
            className="w-48 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm uppercase placeholder:normal-case placeholder:lowercase focus:border-blue-400 focus:outline-none"
          />
          <button
            type="button"
            onClick={onSearch}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            查询
          </button>
          <button
            type="button"
            onClick={() => {
              setTicker('')
              setAppliedTicker('')
              void fetchRuns('')
            }}
            title="刷新"
            className="rounded-lg border border-gray-200 bg-white p-2 text-gray-500 hover:bg-gray-50"
          >
            <RefreshCcw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-700">
          {error}
        </div>
      )}

      <div className="rounded-2xl border border-gray-200 bg-white shadow-sm">
        <div className="border-b border-gray-100 px-5 py-3 text-sm text-gray-500">
          {loading ? (
            <span className="inline-flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> 正在拉取
            </span>
          ) : (
            <span>
              {appliedTicker ? `标的 ${appliedTicker} · ${runs.length} 条` : `最近 ${runs.length} 条`}
            </span>
          )}
        </div>
        {runs.length === 0 && !loading ? (
          <div className="px-5 py-12 text-center text-sm text-gray-400">
            暂无历史运行 —— 到
            <Link href="/trading-desk" className="mx-1 text-blue-600 hover:underline">交易台</Link>
            跑一次吧。
          </div>
        ) : (
          <ul className="divide-y divide-gray-100">
            {runs.map((r) => {
              const status = STATUS_LABEL[r.status] ?? STATUS_LABEL.interrupted
              return (
                <li key={r.run_id}>
                  <Link
                    href={`/trading-desk/history/${r.run_id}`}
                    className="flex items-center gap-4 px-5 py-4 transition-colors hover:bg-blue-50/40"
                  >
                    <div className="flex w-28 flex-col items-start">
                      <span className="text-lg font-semibold tracking-tight text-gray-900">{r.ticker}</span>
                      <span className="font-mono text-[11px] text-gray-400">{r.trade_date}</span>
                    </div>
                    <VerdictBadge signal={r.verdict_signal} confidence={r.verdict_confidence} />
                    <span className={`rounded-md border px-2 py-0.5 text-xs ${status.tone}`}>
                      {status.label}
                    </span>
                    <div className="hidden flex-1 items-center gap-4 text-xs text-gray-500 sm:flex">
                      <span className="inline-flex items-center gap-1">
                        <Clock className="h-3.5 w-3.5" />
                        {formatDuration(r.duration_ms)}
                      </span>
                      <span>{r.signals_count} 信号</span>
                      <span>{r.turns_count} 卡片</span>
                      <span className="font-mono text-[11px] text-gray-400">{r.engine}</span>
                    </div>
                    <div className="text-right text-xs text-gray-400">
                      <div>{formatTimestamp(r.finished_at ?? r.created_at)}</div>
                    </div>
                  </Link>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </DashboardShell>
  )
}