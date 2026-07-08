'use client'

import { useEffect, useState } from 'react'
import DashboardShell from '@/components/layout/DashboardShell'
import { supplyGraphApi } from '@/lib/api/supplyGraph'

type Run = { id: string; universe: string; status: string; total: number; completed: number; failed: number; created_at: string }

export default function SupplyGraphTasksPage() {
  const [runs, setRuns] = useState<Run[]>([])
  useEffect(() => { void supplyGraphApi.runs().then(setRuns) }, [])
  return <DashboardShell><main className="min-h-screen bg-slate-50 p-8"><div className="mx-auto max-w-6xl"><h1 className="text-3xl font-bold">供应链任务看板</h1><p className="mb-6 mt-1 text-slate-500">批次进度、配额等待与失败重试一览。</p><div className="overflow-hidden rounded-2xl border bg-white shadow-sm"><table className="w-full text-left text-sm"><thead className="bg-slate-100 text-slate-600"><tr>{['范围','状态','进度','失败','创建时间'].map((name) => <th key={name} className="px-5 py-3">{name}</th>)}</tr></thead><tbody>{runs.map((run) => <tr key={run.id} className="border-t"><td className="px-5 py-4 font-medium">{run.universe}</td><td className="px-5 py-4"><span className="rounded-full bg-blue-50 px-3 py-1 text-blue-700">{run.status}</span></td><td className="px-5 py-4">{run.completed} / {run.total}</td><td className="px-5 py-4 text-red-600">{run.failed}</td><td className="px-5 py-4 text-slate-500">{new Date(run.created_at).toLocaleString()}</td></tr>)}</tbody></table></div></div></main></DashboardShell>
}
