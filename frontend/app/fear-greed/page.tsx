'use client'

import { useEffect, useState, useCallback } from 'react'
import { useFearGreedStore } from '@/lib/store/fear_greed'
import FearGreedChart from '@/components/fear_greed/FearGreedChart'
import { FearGreedSnapshot } from '@/lib/api/fear_greed'
import Spinner from '@/components/ui/Spinner'
import { getRatingColor, getRatingLabel } from '@/lib/constants/fearGreed'
import DashboardShell from '@/components/layout/DashboardShell'

// Time range options
const TIME_RANGES = [
  { label: '1个月', days: 30 },
  { label: '3个月', days: 90 },
  { label: '6个月', days: 180 },
  { label: '1年', days: 365 },
  { label: '2年', days: 730 },
  { label: '5年', days: 1825 },
]

interface StatCardProps {
  label: string
  snapshot: FearGreedSnapshot
  icon?: string
}

function StatCard({ label, snapshot, icon }: StatCardProps) {
  const color = getRatingColor(snapshot.rating)
  return (
    <div 
      className="group relative bg-white rounded-2xl border border-gray-100 p-5 flex flex-col gap-2 hover:shadow-lg hover:border-gray-200 transition-all duration-300 overflow-hidden"
    >
      {/* 渐变背景装饰 */}
      <div 
        className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300"
        style={{
          background: `linear-gradient(135deg, ${color}08 0%, ${color}03 100%)`,
        }}
      />
      
      <div className="relative">
        {icon && (
          <div className="text-2xl mb-1">{icon}</div>
        )}
        <div className="text-xs text-gray-500 font-semibold uppercase tracking-wider">{label}</div>
        <div 
          className="text-3xl font-bold mt-1 tracking-tight" 
          style={{ color }}
        >
          {Math.round(snapshot.score)}
        </div>
        <div 
          className="text-xs font-semibold mt-1 uppercase tracking-wide" 
          style={{ color }}
        >
          {getRatingLabel(snapshot.rating)}
        </div>
        {snapshot.date && (
          <div className="text-xs text-gray-400 mt-2 font-medium">{snapshot.date}</div>
        )}
      </div>
    </div>
  )
}

export default function FearGreedPage() {
  const { data, loading, error, fetchData } = useFearGreedStore()
  const [selectedRange, setSelectedRange] = useState<number>(365)

  const loadData = useCallback((days: number) => {
    const endDate = new Date()
    const startDate = new Date()
    startDate.setDate(startDate.getDate() - days)
    
    const startStr = startDate.toISOString().split('T')[0]
    const endStr = endDate.toISOString().split('T')[0]
    
    fetchData(startStr, endStr)
  }, [fetchData])

  useEffect(() => {
    loadData(selectedRange)
  }, [loadData, selectedRange])

  const handleRangeChange = (days: number) => {
    setSelectedRange(days)
    loadData(days)
  }

  return (
    <DashboardShell>
      <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="max-w-7xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex flex-col gap-2">
          <h1 className="text-3xl font-extrabold text-gray-900 tracking-tight">
            恐慌与贪婪指数
          </h1>
          <p className="text-gray-500 max-w-2xl leading-relaxed font-medium">
            实时监测市场情绪风向标，同步 CNN Fear & Greed Index 权威数据，助您捕捉市场极端情绪下的投资机会。
          </p>
          <div className="flex items-center gap-2 mt-1">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <span className="text-xs text-gray-400 font-bold uppercase tracking-widest">每小时自动更新</span>
          </div>
        </div>

        {/* Chart Section */}
        <div className="bg-white/80 backdrop-blur-md rounded-2xl border border-blue-50 shadow-sm p-8">
          {/* Time Range Selector */}
          <div className="flex flex-col md:flex-row items-center justify-between gap-4 mb-8">
            <div className="flex items-center gap-2 bg-gray-100/50 p-1 rounded-xl">
              {TIME_RANGES.map((range) => (
                <button
                  key={range.days}
                  onClick={() => handleRangeChange(range.days)}
                  className={`px-4 py-2 rounded-lg text-sm font-bold transition-all duration-300 ${
                    selectedRange === range.days
                      ? 'bg-blue-600 text-white shadow-lg shadow-blue-200'
                      : 'text-gray-500 hover:text-gray-900 hover:bg-white'
                  }`}
                >
                  {range.label}
                </button>
              ))}
            </div>
            {data && (
              <div className="px-4 py-2 bg-blue-50 rounded-lg border border-blue-100 text-xs font-bold text-blue-600 tracking-wider">
                {data.history.length > 0 && (
                  <span>
                    {data.history[0]?.date} — {data.history[data.history.length - 1]?.date}
                  </span>
                )}
              </div>
            )}
          </div>

          {loading && (
            <div className="flex items-center justify-center h-[340px]">
              <Spinner size={40} />
            </div>
          )}
          {error && !loading && (
            <div className="flex items-center justify-center h-[340px] text-red-500 text-sm font-medium">
              {error}
            </div>
          )}
          {data && !loading && (
            <FearGreedChart 
              history={data.history} 
              current={data.current}
            />
          )}
        </div>

        {/* Stats Grid */}
        {data && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
            <StatCard 
              label="前一周" 
              snapshot={data.previous_week} 
              icon="📅"
            />
            <StatCard 
              label="前一月" 
              snapshot={data.previous_month} 
              icon="📆"
            />
            <StatCard 
              label="前一年" 
              snapshot={data.previous_year} 
              icon="🗓️"
            />
            <StatCard 
              label="历史最低" 
              snapshot={data.history_low} 
              icon="⬇️"
            />
            <StatCard 
              label="历史最高" 
              snapshot={data.history_high} 
              icon="⬆️"
            />
            <StatCard 
              label="今日" 
              snapshot={data.current} 
              icon="✨"
            />
          </div>
        )}
      </div>
      </div>
    </DashboardShell>
  )
}
