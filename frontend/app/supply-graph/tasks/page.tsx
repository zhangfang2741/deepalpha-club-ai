'use client'

import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import DashboardShell from '@/components/layout/DashboardShell'
import {
  supplyGraphApi,
  type SupplyRun,
  type SupplyTask,
} from '@/lib/api/supplyGraph'
import { AlertCircle, Loader2, Pause, Play, RefreshCw, RotateCcw } from 'lucide-react'

const UNIVERSES: { value: string; label: string }[] = [
  { value: 'sp500', label: 'S&P 500' },
  { value: 'nasdaq100', label: 'Nasdaq 100' },
  { value: 'russell1000', label: 'Russell 1000' },
]

// 运行/任务状态到中文与配色的统一映射
const STATUS_META: Record<string, { label: string; className: string }> = {
  pending: { label: '待处理', className: 'bg-slate-100 text-slate-600' },
  queued: { label: '排队中', className: 'bg-slate-100 text-slate-600' },
  running: { label: '运行中', className: 'bg-blue-50 text-blue-700' },
  retrying: { label: '重试中', className: 'bg-amber-50 text-amber-700' },
  paused: { label: '已暂停', className: 'bg-amber-100 text-amber-800' },
  paused_quota: { label: '配额等待', className: 'bg-purple-50 text-purple-700' },
  success: { label: '成功', className: 'bg-emerald-50 text-emerald-700' },
  done: { label: '已完成', className: 'bg-emerald-50 text-emerald-700' },
  failed: { label: '失败', className: 'bg-red-50 text-red-700' },
}

const statusMeta = (status: string) =>
  STATUS_META[status] ?? { label: status, className: 'bg-slate-100 text-slate-600' }

function StatusBadge({ status }: { status: string }) {
  const meta = statusMeta(status)
  return (
    <span className={`inline-block rounded-full px-3 py-1 text-xs font-medium ${meta.className}`}>
      {meta.label}
    </span>
  )
}

function ProgressBar({ run }: { run: SupplyRun }) {
  const total = run.total || 0
  const completedPct = total ? (run.completed / total) * 100 : 0
  const failedPct = total ? (run.failed / total) * 100 : 0
  return (
    <div className="min-w-[120px]">
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-slate-100">
        <div className="bg-emerald-500" style={{ width: `${completedPct}%` }} />
        <div className="bg-red-500" style={{ width: `${failedPct}%` }} />
      </div>
      <p className="mt-1 text-xs text-slate-500">
        {run.completed} / {total}
        {run.failed > 0 && <span className="ml-1 text-red-600">· 失败 {run.failed}</span>}
      </p>
    </div>
  )
}

const fmtTime = (value: string | null) => (value ? new Date(value).toLocaleString() : '—')

function TaskTable({ tasks }: { tasks: SupplyTask[] }) {
  const [onlyFailed, setOnlyFailed] = useState(false)
  const rows = onlyFailed ? tasks.filter((t) => t.status === 'failed') : tasks
  const failedCount = tasks.filter((t) => t.status === 'failed').length
  if (tasks.length === 0) {
    return <p className="px-5 py-4 text-sm text-slate-500">该批次暂无子任务（可能尚未展开或已完成）。</p>
  }
  return (
    <div className="px-5 py-4">
      <div className="mb-3 flex items-center gap-3 text-xs text-slate-500">
        <span>共 {tasks.length} 家公司</span>
        {failedCount > 0 && (
          <label className="inline-flex cursor-pointer items-center gap-1.5">
            <input
              type="checkbox"
              checked={onlyFailed}
              onChange={(e) => setOnlyFailed(e.target.checked)}
              className="cursor-pointer"
            />
            仅看失败（{failedCount}）
          </label>
        )}
      </div>
      <div className="max-h-80 overflow-auto rounded-lg border">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 bg-slate-50 text-xs text-slate-500">
            <tr>
              {['公司', '阶段', '状态', '重试', '错误信息', '完成时间'].map((h) => (
                <th key={h} className="px-4 py-2 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((task) => (
              <tr key={task.id} className="border-t align-top">
                <td className="px-4 py-2 font-medium text-slate-800">{task.ticker}</td>
                <td className="px-4 py-2 text-slate-500">{task.stage}</td>
                <td className="px-4 py-2">
                  <StatusBadge status={task.status} />
                </td>
                <td className="px-4 py-2 text-slate-500">
                  {task.retries}/{task.max_retries}
                </td>
                <td className="max-w-xs px-4 py-2 text-xs text-red-600">
                  {task.error ? <span className="line-clamp-2 break-words">{task.error}</span> : '—'}
                </td>
                <td className="px-4 py-2 text-xs text-slate-400">{fmtTime(task.finished_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function SupplyGraphTasksPage() {
  const [runs, setRuns] = useState<SupplyRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [creating, setCreating] = useState(false)
  const [universe, setUniverse] = useState('sp500')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [tasks, setTasks] = useState<SupplyTask[]>([])
  const [tasksLoading, setTasksLoading] = useState(false)
  const [pendingAction, setPendingAction] = useState<string | null>(null)
  const expandedRef = useRef<string | null>(null)

  useEffect(() => {
    expandedRef.current = expandedId
  }, [expandedId])

  const loadRuns = useCallback(async () => {
    try {
      const data = await supplyGraphApi.runs()
      setRuns(data)
      setError('')
    } catch {
      setError('加载任务列表失败，请稍后重试。')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadTasks = useCallback(async (runId: string) => {
    setTasksLoading(true)
    try {
      const detail = await supplyGraphApi.run(runId)
      if (expandedRef.current === runId) {
        setTasks(detail.tasks)
        setRuns((prev) => prev.map((r) => (r.id === runId ? detail.run : r)))
      }
    } catch {
      if (expandedRef.current === runId) setTasks([])
    } finally {
      setTasksLoading(false)
    }
  }, [])

  // 首次挂载加载（用 promise 回调设置状态，避免 effect 内同步 setState）
  useEffect(() => {
    let active = true
    supplyGraphApi
      .runs()
      .then((data) => {
        if (active) {
          setRuns(data)
          setError('')
        }
      })
      .catch(() => {
        if (active) setError('加载任务列表失败，请稍后重试。')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  // 自动刷新：列表 + 当前展开批次的子任务
  useEffect(() => {
    if (!autoRefresh) return
    const timer = window.setInterval(() => {
      void loadRuns()
      if (expandedRef.current) void loadTasks(expandedRef.current)
    }, 5000)
    return () => window.clearInterval(timer)
  }, [autoRefresh, loadRuns, loadTasks])

  const toggleExpand = useCallback(
    (runId: string) => {
      if (expandedId === runId) {
        setExpandedId(null)
        setTasks([])
        return
      }
      setExpandedId(runId)
      setTasks([])
      void loadTasks(runId)
    },
    [expandedId, loadTasks],
  )

  const createRun = useCallback(async () => {
    setCreating(true)
    try {
      await supplyGraphApi.createRun(universe)
      await loadRuns()
    } catch {
      setError('新建批次失败，请稍后重试。')
    } finally {
      setCreating(false)
    }
  }, [universe, loadRuns])

  const runAction = useCallback(
    async (runId: string, action: 'pause' | 'resume' | 'retry') => {
      setPendingAction(`${runId}:${action}`)
      try {
        if (action === 'pause') await supplyGraphApi.pauseRun(runId)
        else if (action === 'resume') await supplyGraphApi.resumeRun(runId)
        else await supplyGraphApi.retryFailed(runId)
        await loadRuns()
        if (expandedRef.current === runId) await loadTasks(runId)
      } catch {
        setError('操作失败，请稍后重试。')
      } finally {
        setPendingAction(null)
      }
    },
    [loadRuns, loadTasks],
  )

  const isBusy = (runId: string, action: string) => pendingAction === `${runId}:${action}`

  return (
    <DashboardShell>
      <main className="min-h-screen bg-slate-50 p-4 sm:p-8">
        <div className="mx-auto max-w-6xl">
          <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h1 className="text-3xl font-bold text-slate-900">供应链任务看板</h1>
              <p className="mt-1 text-slate-500">批次进度、配额等待与失败重试一览，失败任务可一键继续。</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={universe}
                onChange={(e) => setUniverse(e.target.value)}
                className="cursor-pointer rounded-xl border bg-white px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                {UNIVERSES.map((u) => (
                  <option key={u.value} value={u.value}>
                    {u.label}
                  </option>
                ))}
              </select>
              <button
                onClick={createRun}
                disabled={creating}
                className="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 focus-visible:ring-2 focus-visible:ring-blue-500 disabled:cursor-wait disabled:opacity-60"
              >
                {creating && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                新建批次
              </button>
              <button
                onClick={() => void loadRuns()}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl border bg-white px-3 py-2 text-sm text-slate-600 transition-colors hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
                刷新
              </button>
              <label className="inline-flex cursor-pointer items-center gap-1.5 text-sm text-slate-600">
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                  className="cursor-pointer"
                />
                自动刷新
              </label>
            </div>
          </header>

          {error && (
            <div className="mb-4 flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              {error}
            </div>
          )}

          <div className="overflow-hidden rounded-2xl border bg-white shadow-sm">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-100 text-slate-600">
                <tr>
                  {['范围', '类型', '状态', '进度', '创建时间', '操作'].map((name) => (
                    <th key={name} className="px-5 py-3 font-medium">
                      {name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={6} className="px-5 py-10 text-center text-slate-400">
                      <Loader2 className="mx-auto h-5 w-5 animate-spin" aria-hidden="true" />
                    </td>
                  </tr>
                ) : runs.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-5 py-10 text-center text-slate-400">
                      暂无任务，点击「新建批次」开始一次全量供应链图谱构建。
                    </td>
                  </tr>
                ) : (
                  runs.map((run) => {
                    const canPause = ['running', 'pending'].includes(run.status)
                    const canResume = ['paused', 'paused_quota'].includes(run.status)
                    const canRetry = run.failed > 0
                    const expanded = expandedId === run.id
                    return (
                      <Fragment key={run.id}>
                        <tr className="border-t hover:bg-slate-50/60">
                          <td className="px-5 py-4">
                            <button
                              onClick={() => toggleExpand(run.id)}
                              className="cursor-pointer font-medium text-slate-800 hover:text-blue-600"
                            >
                              {expanded ? '▾' : '▸'} {run.universe}
                            </button>
                          </td>
                          <td className="px-5 py-4 text-slate-500">
                            {run.run_type === 'batch' ? '批次' : '单公司'}
                          </td>
                          <td className="px-5 py-4">
                            <StatusBadge status={run.status} />
                          </td>
                          <td className="px-5 py-4">
                            <ProgressBar run={run} />
                          </td>
                          <td className="px-5 py-4 text-xs text-slate-400">{fmtTime(run.created_at)}</td>
                          <td className="px-5 py-4">
                            <div className="flex flex-wrap gap-1.5">
                              {canPause && (
                                <button
                                  onClick={() => runAction(run.id, 'pause')}
                                  disabled={isBusy(run.id, 'pause')}
                                  className="inline-flex cursor-pointer items-center gap-1 rounded-lg border px-2.5 py-1 text-xs text-amber-700 transition-colors hover:bg-amber-50 disabled:opacity-50"
                                >
                                  <Pause className="h-3 w-3" aria-hidden="true" />
                                  暂停
                                </button>
                              )}
                              {canResume && (
                                <button
                                  onClick={() => runAction(run.id, 'resume')}
                                  disabled={isBusy(run.id, 'resume')}
                                  className="inline-flex cursor-pointer items-center gap-1 rounded-lg border px-2.5 py-1 text-xs text-blue-700 transition-colors hover:bg-blue-50 disabled:opacity-50"
                                >
                                  <Play className="h-3 w-3" aria-hidden="true" />
                                  继续
                                </button>
                              )}
                              {canRetry && (
                                <button
                                  onClick={() => runAction(run.id, 'retry')}
                                  disabled={isBusy(run.id, 'retry')}
                                  className="inline-flex cursor-pointer items-center gap-1 rounded-lg border px-2.5 py-1 text-xs text-slate-700 transition-colors hover:bg-slate-100 disabled:opacity-50"
                                >
                                  <RotateCcw className="h-3 w-3" aria-hidden="true" />
                                  重试失败
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                        {expanded && (
                          <tr className="border-t bg-slate-50/40">
                            <td colSpan={6} className="p-0">
                              {tasksLoading && tasks.length === 0 ? (
                                <p className="flex items-center gap-2 px-5 py-4 text-sm text-slate-400">
                                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                                  正在加载子任务…
                                </p>
                              ) : (
                                <TaskTable tasks={tasks} />
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </DashboardShell>
  )
}
