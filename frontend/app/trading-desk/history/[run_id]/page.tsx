'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { use } from 'react'
import {
  AlertTriangle, ArrowLeft, Calendar, Clock, Gavel, History,
  Loader2, RefreshCcw,
} from 'lucide-react'
import DashboardShell from '@/components/layout/DashboardShell'
import TurnReplayCard from '@/components/trading_desk/TurnReplayCard'
import { getApiErrorMessage } from '@/lib/api/client'
import {
  getRun, type RunDetailResponse, type SignalRecord, type VerdictData,
} from '@/lib/api/trading_desk'

const ACTION: Record<VerdictData['signal'], { label: string; color: string }> = {
  BUY: { label: '买入', color: 'text-emerald-600' },
  SELL: { label: '卖出', color: 'text-red-500' },
  HOLD: { label: '观望', color: 'text-amber-600' },
}

const STATUS_TONE: Record<RunDetailResponse['status'], string> = {
  running: 'bg-blue-50 text-blue-700 border-blue-200',
  completed: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  cancelled: 'bg-gray-100 text-gray-600 border-gray-200',
  failed: 'bg-red-50 text-red-700 border-red-200',
  interrupted: 'bg-amber-50 text-amber-700 border-amber-200',
}

const STATUS_LABEL: Record<RunDetailResponse['status'], string> = {
  running: '运行中',
  completed: '已完成',
  cancelled: '已取消',
  failed: '失败',
  interrupted: '中断',
}

function formatDuration(ms: number): string {
  if (!ms || ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  const m = Math.floor(ms / 60_000)
  const s = Math.floor((ms % 60_000) / 1000)
  return `${m}m${s}s`
}

function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN', { hour12: false })
}

export default function TradingDeskRunReplayPage({
  params,
}: {
  params: Promise<{ run_id: string }>
}) {
  // Next.js 16 把 params 改成 Promise —— 必须 await/use 解开
  const { run_id } = use(params)
  const [detail, setDetail] = useState<RunDetailResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)

  const fetchDetail = useCallback(async () => {
    setLoading(true)
    setError(null)
    setNotFound(false)
    try {
      const data = await getRun(run_id)
      setDetail(data)
    } catch (err) {
      const msg = getApiErrorMessage(err)
      // 404 是越权或不存在的统一反馈，不算错
      if (msg.includes('404') || msg.includes('运行不存在')) {
        setNotFound(true)
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
    }
  }, [run_id])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 数据获取模式：mount 后拉一次
    void fetchDetail()
  }, [fetchDetail])

  // 把 signals 按 turn_id 索引，让对应卡片顺手拿到信号
  const signalByTurnId = useMemo(() => {
    const map = new Map<string, SignalRecord>()
    if (!detail) return map
    for (const s of detail.signals) {
      if (s.turn_id) map.set(s.turn_id, s)
    }
    return map
  }, [detail])

  // 没有 turn_id 的信号另起一栏「无主信号」
  const orphanSignals = useMemo<SignalRecord[]>(() => {
    if (!detail) return []
    return detail.signals.filter((s) => !s.turn_id)
  }, [detail])

  if (notFound) {
    return (
      <DashboardShell>
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-8 text-center">
          <History className="mx-auto mb-3 h-10 w-10 text-amber-500" />
          <p className="text-base font-medium text-amber-800">该运行不存在或已过期</p>
          <p className="mt-1 text-sm text-amber-700">事件流 7 天后自动清理；超出窗口的 run 无法查看。</p>
          <Link
            href="/trading-desk/history"
            className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-amber-300 bg-white px-4 py-2 text-sm text-amber-700 hover:bg-amber-50"
          >
            <ArrowLeft className="h-4 w-4" /> 返回列表
          </Link>
        </div>
      </DashboardShell>
    )
  }

  return (
    <DashboardShell>
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Link
            href="/trading-desk/history"
            className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-600 hover:bg-gray-50"
          >
            <ArrowLeft className="h-4 w-4" />
            返回列表
          </Link>
          {detail && (
            <>
              <h1 className="flex items-center gap-2 text-2xl font-semibold text-gray-900">
                <span className="font-mono tracking-tight">{detail.ticker}</span>
                <span className={`rounded-md border px-2 py-0.5 text-xs ${STATUS_TONE[detail.status]}`}>
                  {STATUS_LABEL[detail.status]}
                </span>
              </h1>
              <span className="font-mono text-[11px] text-gray-400">{detail.engine}</span>
            </>
          )}
        </div>
        <button
          type="button"
          onClick={() => void fetchDetail()}
          title="刷新"
          className="flex items-center gap-1.5 self-start rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 sm:self-auto"
        >
          <RefreshCcw className="h-4 w-4" /> 刷新
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-700">
          {error}
        </div>
      )}

      {loading || !detail ? (
        <div className="flex items-center justify-center rounded-2xl border border-gray-200 bg-white py-20">
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
          <span className="ml-2 text-sm text-gray-500">正在加载...</span>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_19rem]">
          {/* 左：时间线 */}
          <div className="flex flex-col gap-3">
            {detail.turns.length === 0 ? (
              <div className="rounded-2xl border border-gray-200 bg-white px-5 py-12 text-center text-sm text-gray-400">
                该运行未产出任何 turn（可能在中途中断或尚未启动）。
              </div>
            ) : (
              detail.turns.map((turn) => (
                <TurnReplayCard
                  key={turn.turn_id}
                  turn={turn}
                  signal={signalByTurnId.get(turn.turn_id) ?? null}
                />
              ))
            )}
            {orphanSignals.length > 0 && (
              <div className="rounded-xl border border-gray-200 bg-gray-50/60 p-3 text-xs text-gray-500">
                <span className="font-medium text-gray-700">未关联卡片：</span>
                {' '}
                {orphanSignals.map((s) => `${s.name} ${s.dir} ${s.conf}`).join(' / ')}
              </div>
            )}
          </div>

          {/* 右：元数据 + 裁决 */}
          <aside className="flex flex-col gap-3 lg:sticky lg:top-4 lg:self-start">
            <RunMetaCard detail={detail} />
            {detail.verdict ? <VerdictPanel verdict={detail.verdict} /> : (
              <div className="rounded-xl border border-gray-200 bg-gray-50/60 p-4 text-center text-xs text-gray-400">
                <Gavel className="mx-auto mb-1 h-5 w-5 text-gray-300" />
                本次未产出裁决
              </div>
            )}
          </aside>
        </div>
      )}
    </DashboardShell>
  )
}

function RunMetaCard({ detail }: { detail: RunDetailResponse }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 text-sm">
      <div className="mb-3 font-mono text-[11px] uppercase tracking-wide text-gray-400">运行元数据</div>
      <dl className="space-y-2 text-[12.5px]">
        <Row label="交易日期" value={detail.trade_date} />
        <Row label="引擎" value={<span className="font-mono text-[11px]">{detail.engine}</span>} />
        <Row
          label="耗时"
          value={
            <span className="inline-flex items-center gap-1 font-mono text-[12px]">
              <Clock className="h-3.5 w-3.5 text-gray-400" /> {formatDuration(detail.duration_ms)}
            </span>
          }
        />
        <Row
          label="开始"
          value={
            <span className="inline-flex items-center gap-1 font-mono text-[11px] text-gray-500">
              <Calendar className="h-3.5 w-3.5 text-gray-400" /> {formatTimestamp(detail.created_at)}
            </span>
          }
        />
        <Row label="结束" value={<span className="font-mono text-[11px] text-gray-500">{formatTimestamp(detail.finished_at) || '—'}</span>} />
        <Row label="卡片" value={`${detail.turns.length} 张`} />
        <Row label="信号" value={`${detail.signals.length} 条`} />
        <Row label="Run ID" value={<span className="break-all font-mono text-[10px] text-gray-400">{detail.run_id}</span>} />
      </dl>
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-gray-100 pb-1.5 last:border-0 last:pb-0">
      <dt className="text-[11px] text-gray-400">{label}</dt>
      <dd className="text-right text-gray-700">{value}</dd>
    </div>
  )
}

function VerdictPanel({ verdict }: { verdict: VerdictData }) {
  const action = ACTION[verdict.signal]
  const confPct = Math.round(verdict.confidence * 100)
  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50/70 p-4">
      <div className="flex items-baseline justify-between">
        <span className={`text-2xl font-extrabold ${action.color}`}>{action.label}</span>
        <span className="font-mono text-[11px] text-gray-500">
          置信度 <b className="text-sm text-gray-900">{confPct}%</b>
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2.5">
        <Field label="仓位" value={`${(verdict.size_fraction * 100).toFixed(1)}%`} />
        <Field label="止损" value={verdict.stop_loss != null ? String(verdict.stop_loss) : '—'} />
        <Field label="目标价" value={verdict.target_price != null ? String(verdict.target_price) : '—'} />
        <Field
          label="周期"
          value={verdict.time_horizon_days != null ? `${verdict.time_horizon_days} 天` : '—'}
        />
      </div>

      {verdict.warning_message && (
        <div className="mt-3 flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-none text-amber-600" />
          <p className="text-[11.5px] leading-relaxed text-amber-800">
            结论解析降级：{verdict.warning_message}
          </p>
        </div>
      )}

      {verdict.rationale && (
        <p className="mt-3 border-t border-gray-200 pt-3 text-[12px] leading-relaxed text-gray-600">
          {verdict.rationale}
        </p>
      )}
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] text-gray-400">{label}</div>
      <div className="mt-0.5 font-mono text-[13px] font-semibold text-gray-900">{value}</div>
    </div>
  )
}