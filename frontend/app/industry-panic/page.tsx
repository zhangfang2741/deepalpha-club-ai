'use client'

import { useEffect, useState } from 'react'
import { fetchIndustryPanic } from '@/lib/api/industry_panic'
import type { IndustryPanicResponse, SectorPanic } from '@/lib/api/industry_panic'
import DashboardShell from '@/components/layout/DashboardShell'
import Spinner from '@/components/ui/Spinner'
import IndustryPanicChart from '@/components/industry_panic/IndustryPanicChart'
import SectorPanicBar from '@/components/industry_panic/SectorPanicBar'
import { getPanicColor, getPanicLevel } from '@/lib/constants/industryPanic'

export default function IndustryPanicPage() {
  const [data, setData] = useState<IndustryPanicResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<SectorPanic | null>(null)

  useEffect(() => {
    setLoading(true)
    fetchIndustryPanic()
      .then((res) => {
        setData(res)
        if (res.sectors.length > 0) {
          // 默认选中恐慌值最高的行业
          const sorted = [...res.sectors].sort(
            (a, b) => (b.current_panic ?? 50) - (a.current_panic ?? 50)
          )
          setSelected(sorted[0])
        }
      })
      .catch(() => setError('数据加载失败，请刷新重试'))
      .finally(() => setLoading(false))
  }, [])

  const currentPanic = selected?.current_panic ?? 50
  const currentRsi = selected?.current_rsi ?? null
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
            基于各 GICS 行业代表性 ETF 的 RSI(14) 衍生：
            <code className="mx-1 px-1.5 py-0.5 bg-gray-100 rounded text-xs font-mono">panic = 100 − RSI</code>
            。价格急跌（超卖）→ RSI 低 → 恐慌高；价格强势（超买）→ RSI 高 → 恐慌低。
          </p>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <span className="text-xs text-gray-400 font-bold uppercase tracking-widest">
              数据来源：SPDR 行业 ETF 日线 · 每小时缓存
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
                  <span className="text-xs text-gray-400 font-normal">截至 {data.as_of}</span>
                </div>
                <SectorPanicBar
                  sectors={data.sectors}
                  selectedSymbol={selected?.symbol ?? ''}
                  onSelect={setSelected}
                />
              </div>
            </div>

            {/* 右侧：历史恐慌走势图 */}
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
                        <span className={`text-xs font-bold px-2 py-1 rounded-lg ${currentLevel.badgeClass}`}>
                          {currentLevel.label}
                        </span>
                      </div>
                      <div className="text-xs text-gray-400 mt-0.5">
                        {selected.symbol} · 历史恐慌走势（近 1 年日线）
                      </div>
                    </div>
                    <div className="text-right">
                      <div
                        className="text-3xl font-bold tabular-nums"
                        style={{ color: currentColor }}
                      >
                        {Math.round(currentPanic)}
                      </div>
                      {currentRsi !== null && (
                        <div className="text-xs text-gray-400 font-mono mt-0.5">
                          RSI {currentRsi.toFixed(1)}
                        </div>
                      )}
                    </div>
                  </div>

                  {selected.history.length > 0 ? (
                    <IndustryPanicChart sector={selected} />
                  ) : (
                    <div className="flex items-center justify-center h-[300px] text-gray-400 text-sm">
                      该行业数据暂不可用
                    </div>
                  )}

                  {/* RSI 阈值说明 */}
                  <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-xs text-gray-500">
                    <span>RSI &lt; 30 → 超卖 → <span className="text-red-500 font-bold">panic &gt; 70</span></span>
                    <span>RSI = 50 → 中性 → <span className="text-yellow-600 font-bold">panic = 50</span></span>
                    <span>RSI &gt; 70 → 超买 → <span className="text-blue-500 font-bold">panic &lt; 30</span></span>
                  </div>
                </div>
              )}

              {/* 计算方法 */}
              <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl text-sm">
                <div className="font-semibold text-slate-700 mb-2">计算方法</div>
                <div className="space-y-1.5 text-slate-600 text-xs">
                  <div>
                    <span className="font-medium text-slate-800">数据来源</span>
                    ：各 GICS 行业 SPDR ETF（XLK / XLV / XLF / XLY / XLP / XLI / XLE / XLB / XLC / XLRE / XLU）日收盘价
                  </div>
                  <div>
                    <span className="font-medium text-slate-800">RSI(14)</span>
                    ：Wilder 平滑法，14 日平均涨幅 / 平均跌幅，衡量价格动量强弱
                  </div>
                  <div>
                    <span className="font-medium text-slate-800">恐慌映射</span>
                    ：
                    <code className="mx-1 px-1.5 py-0.5 bg-white border border-slate-200 rounded font-mono text-slate-700">
                      panic = 100 − RSI
                    </code>
                    ，区间 [0, 100]
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1">
                    <span><span className="text-red-500 font-bold">≥ 80</span> 极度恐慌</span>
                    <span><span className="text-orange-500 font-bold">60-80</span> 恐慌</span>
                    <span><span className="text-yellow-600 font-bold">40-60</span> 中性</span>
                    <span><span className="text-blue-500 font-bold">20-40</span> 平静</span>
                    <span><span className="text-blue-700 font-bold">≤ 20</span> 极度平静</span>
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
