'use client'

import { useEffect } from 'react'
import { useFearGreedStore } from '@/lib/store/fear_greed'
import FearGreedChart from '@/components/fear_greed/FearGreedChart'
import { FearGreedSnapshot } from '@/lib/api/fear_greed'

const RATING_LABEL: Record<string, string> = {
  'Extreme Greed': '极度贪婪',
  'Greed': '贪婪',
  'Neutral': '中性',
  'Fear': '恐惧',
  'Extreme Fear': '极度恐惧',
}

const RATING_COLOR: Record<string, string> = {
  'Extreme Greed': '#16a34a',
  'Greed': '#4ade80',
  'Neutral': '#ca8a04',
  'Fear': '#f87171',
  'Extreme Fear': '#ef4444',
}

interface StatCardProps {
  label: string
  snapshot: FearGreedSnapshot
}

function StatCard({ label, snapshot }: StatCardProps) {
  const color = RATING_COLOR[snapshot.rating] ?? '#6b7280'
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 flex flex-col gap-1">
      <div className="text-xs text-gray-500 font-medium">{label}</div>
      <div className="text-2xl font-bold" style={{ color }}>
        {Math.round(snapshot.score)}
      </div>
      <div className="text-xs font-medium" style={{ color }}>
        {RATING_LABEL[snapshot.rating] ?? snapshot.rating}
      </div>
      {snapshot.date && (
        <div className="text-xs text-gray-400 mt-0.5">{snapshot.date}</div>
      )}
    </div>
  )
}

export default function FearGreedPage() {
  const { data, loading, error, fetchData } = useFearGreedStore()

  useEffect(() => {
    fetchData()
  }, [fetchData])

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">恐慌与贪婪指数</h1>
          <p className="text-sm text-gray-500 mt-1">
            数据来源：CNN Fear &amp; Greed Index · 每小时更新
          </p>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-6">
          {loading && (
            <div className="flex items-center justify-center h-[340px] text-gray-400 text-sm">
              加载中...
            </div>
          )}
          {error && !loading && (
            <div className="flex items-center justify-center h-[340px] text-red-500 text-sm">
              {error}
            </div>
          )}
          {data && !loading && (
            <FearGreedChart history={data.history} current={data.current} />
          )}
        </div>

        {data && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
            <StatCard label="前一周" snapshot={data.previous_week} />
            <StatCard label="前一月" snapshot={data.previous_month} />
            <StatCard label="前一年" snapshot={data.previous_year} />
            <StatCard label="历史最低" snapshot={data.history_low} />
            <StatCard label="历史最高" snapshot={data.history_high} />
            <StatCard label="今日" snapshot={data.current} />
          </div>
        )}
      </div>
    </div>
  )
}
