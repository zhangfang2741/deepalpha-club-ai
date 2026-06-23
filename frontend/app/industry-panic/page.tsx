'use client'

import { useEffect, useState } from 'react'
import { fetchGICSValuations } from '@/lib/api/valuation'
import type { GICSValuationResponse, SectorWithIndustries } from '@/lib/api/valuation'
import DashboardShell from '@/components/layout/DashboardShell'
import Spinner from '@/components/ui/Spinner'
import IndustryPanicChart from '@/components/industry_panic/IndustryPanicChart'
import SectorPanicBar from '@/components/industry_panic/SectorPanicBar'
import { zScoreToPanic, getPanicColor, getPanicLevel } from '@/lib/constants/industryPanic'

export default function IndustryPanicPage() {
  const [data, setData] = useState<GICSValuationResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<SectorWithIndustries | null>(null)

  useEffect(() => {
    setLoading(true)
    fetchGICSValuations()
      .then((res) => {
        setData(res)
        if (res.sectors.length > 0) {
          // 默认选中恐慌值最高的行业
          const sorted = [...res.sectors].sort(
            (a, b) => zScoreToPanic(b.z_score) - zScoreToPanic(a.z_score)
          )
          setSelected(sorted[0])
        }
      })
      .catch(() => setError('数据加载失败，请刷新重试'))
      .finally(() => setLoading(false))
  }, [])

  const currentPanic = selected ? zScoreToPanic(selected.z_score) : 50
  const currentLevel = getPanicLevel(currentPanic)
  const currentColor = getPanicColor(currentPanic)

  return (
    <DashboardShell>
      <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
        {/* 页头 */}
        <div className="flex flex-col gap-1.5">
          <h1 className="text-3xl font-extrabold text-gray-900 tracking-tight">
            行业恐慌指数
          </h1>
          <p className="text-gray-500 max-w-2xl leading-relaxed font-medium text-sm">
            基于 GICS 行业 PE 相对历史均值的偏离程度（z-score）计算，量化各行业估值泡沫风险与恐慌程度。
            指数 &gt; 60 代表估值偏高、市场存在恐慌风险；&lt; 40 代表估值被低估、市场处于平静区间。
          </p>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <span className="text-xs text-gray-400 font-bold uppercase tracking-widest">
              数据来源：GICS 行业估值 · 季度更新
            </span>
          </div>
        </div>

        {loading && (
          <div className="flex items-center justify-center h-64">
            <Spinner size={40} />
          </div>
        )}

        {error && !loading && (
          <div className="p-6 bg-red-50 border border-red-200 rounded-xl text-red-600 text-sm font-medium">
            {error}
          </div>
        )}

        {data && !loading && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* 左侧：行业恐慌排行 */}
            <div className="lg:col-span-1">
              <div className="bg-white/80 backdrop-blur-md rounded-2xl border border-gray-100 shadow-sm p-5">
                <div className="text-sm font-bold text-gray-700 mb-4 flex items-center justify-between">
                  <span>行业恐慌排行</span>
                  <span className="text-xs text-gray-400 font-normal">
                    截至 {data.as_of}
                  </span>
                </div>
                <SectorPanicBar
                  sectors={data.sectors}
                  selectedSector={selected?.sector ?? ''}
                  onSelect={setSelected}
                />
              </div>
            </div>

            {/* 右侧：历史恐慌走势图 + 说明 */}
            <div className="lg:col-span-2 space-y-4">
              {selected && (
                <div className="bg-white/80 backdrop-blur-md rounded-2xl border border-blue-50 shadow-sm p-6">
                  {/* 图表标题 */}
                  <div className="flex items-start justify-between mb-5">
                    <div>
                      <div className="flex items-center gap-3">
                        <h2 className="text-xl font-extrabold text-gray-900">
                          {selected.sector_cn}
                        </h2>
                        <span
                          className={`text-xs font-bold px-2 py-1 rounded-lg ${currentLevel.badgeClass}`}
                        >
                          {currentLevel.label}
                        </span>
                      </div>
                      <div className="text-xs text-gray-400 mt-0.5">
                        {selected.sector} · 历史恐慌指数走势（近 5 年季度）
                      </div>
                    </div>
                    <div className="text-right">
                      <div
                        className="text-3xl font-bold tabular-nums"
                        style={{ color: currentColor }}
                      >
                        {Math.round(currentPanic)}
                      </div>
                      {selected.z_score !== null && (
                        <div className="text-xs text-gray-400 font-mono mt-0.5">
                          z = {selected.z_score >= 0 ? '+' : ''}
                          {selected.z_score.toFixed(2)}σ
                        </div>
                      )}
                    </div>
                  </div>

                  {selected.hist_mean !== null && selected.hist_std !== null ? (
                    <IndustryPanicChart sector={selected} />
                  ) : (
                    <div className="flex items-center justify-center h-[300px] text-gray-400 text-sm">
                      该行业历史数据不足，无法计算恐慌指数
                    </div>
                  )}

                  {/* 当前统计 */}
                  <div className="mt-4 grid grid-cols-3 gap-3">
                    <StatItem
                      label="当前 PE"
                      value={selected.current_pe !== null ? selected.current_pe.toFixed(2) : '—'}
                    />
                    <StatItem
                      label="历史均值 μ"
                      value={selected.hist_mean !== null ? selected.hist_mean.toFixed(2) : '—'}
                    />
                    <StatItem
                      label="历史标准差 σ"
                      value={selected.hist_std !== null ? selected.hist_std.toFixed(2) : '—'}
                    />
                  </div>
                </div>
              )}

              {/* 计算方法说明 */}
              <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl text-sm">
                <div className="font-semibold text-slate-700 mb-2">行业恐慌指数计算方法</div>
                <div className="space-y-1.5 text-slate-600 text-xs">
                  <div>
                    <span className="font-medium text-slate-800">① z-score</span>
                    ：
                    <code className="mx-1 px-1.5 py-0.5 bg-white border border-slate-200 rounded font-mono text-slate-700">
                      z = (当前 PE − 历史均值 μ) / 历史标准差 σ
                    </code>
                  </div>
                  <div>
                    <span className="font-medium text-slate-800">② 恐慌指数</span>
                    ：
                    <code className="mx-1 px-1.5 py-0.5 bg-white border border-slate-200 rounded font-mono text-slate-700">
                      panic = clamp(50 + z × 20, 0, 100)
                    </code>
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-2">
                    <span><span className="text-red-500 font-bold">≥ 80</span> 极度恐慌（估值极度高估）</span>
                    <span><span className="text-orange-500 font-bold">60-80</span> 恐慌（高估）</span>
                    <span><span className="text-yellow-600 font-bold">40-60</span> 中性</span>
                    <span><span className="text-blue-500 font-bold">20-40</span> 平静（低估）</span>
                    <span><span className="text-blue-700 font-bold">≤ 20</span> 极度平静（极度低估）</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardShell>
  )
}

function StatItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-slate-50 rounded-lg px-3 py-2.5">
      <div className="text-[10px] text-slate-400 font-medium uppercase tracking-wide">{label}</div>
      <div className="text-sm font-bold text-slate-800 font-mono mt-0.5">{value}</div>
    </div>
  )
}
