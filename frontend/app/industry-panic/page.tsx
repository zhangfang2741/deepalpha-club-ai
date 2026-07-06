'use client'

import { useEffect, useState, useCallback } from 'react'
import { fetchIndustryPanic } from '@/lib/api/industry_panic'
import type { IndustryPanicResponse, SectorPanic } from '@/lib/api/industry_panic'
import DashboardShell from '@/components/layout/DashboardShell'
import Spinner from '@/components/ui/Spinner'
import IndustryPanicChart from '@/components/industry_panic/IndustryPanicChart'
import SectorPanicBar from '@/components/industry_panic/SectorPanicBar'
import SectorValuationGrid from '@/components/valuation/SectorValuationGrid'
import { getRsiColor, getRsiLevel } from '@/lib/constants/industryPanic'

type ActiveTab = 'panic' | 'valuation'

const TAB_LABELS: Record<ActiveTab, string> = {
  panic: '行业 RSI 情绪',
  valuation: '行业估值分析',
}

function getErrorMessage(err: unknown): string {
  const e = err as { response?: { status?: number }; code?: string; message?: string }
  const status = e?.response?.status
  if (status === 404) return '数据接口暂不可用（404），后端服务可能正在更新，请稍后重试'
  if (status === 503 || status === 502) return `服务暂时不可用（${status}），请稍后重试`
  if (status && status >= 500) return `服务器错误（${status}），请稍后重试`
  if (e?.code === 'ECONNABORTED') return '请求超时（数据量较大，请稍后重试）'
  if (status) return `数据加载失败（${status}）`
  return `数据加载失败：${e?.message ?? '网络错误'}`
}

export default function IndustryPanicPage() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('panic')
  const [data, setData] = useState<IndustryPanicResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<SectorPanic | null>(null)

  const loadData = useCallback(() => {
    setLoading(true)
    setError('')
    fetchIndustryPanic()
      .then((res) => {
        setData(res)
        if (res.sectors.length > 0) {
          const sorted = [...res.sectors].sort(
            (a, b) => (a.current_rsi ?? 50) - (b.current_rsi ?? 50)
          )
          setSelected(sorted[0])
        }
      })
      .catch((err) => {
        console.error('[industry-panic] fetch error:', err?.response?.status, err?.response?.data, err?.message, err)
        setError(getErrorMessage(err))
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const currentRsi = selected?.current_rsi ?? 50
  const currentLevel = getRsiLevel(currentRsi)
  const currentColor = getRsiColor(currentRsi)

  return (
    <DashboardShell>
      <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
        {/* 页头 */}
        <div className="flex flex-col gap-1.5">
          <h1 className="text-3xl font-extrabold text-gray-900 tracking-tight">
            行业恐慌
          </h1>
          <p className="text-gray-500 max-w-2xl leading-relaxed font-medium text-sm">
            从「价格动量」与「估值水位」两个维度观察各 GICS 行业的冷热与恐慌程度。
          </p>
        </div>

        {/* 标签切换 */}
        <div className="flex gap-1 border-b border-gray-200">
          {(['panic', 'valuation'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={[
                'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
                activeTab === tab
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700',
              ].join(' ')}
            >
              {TAB_LABELS[tab]}
            </button>
          ))}
        </div>

        {/* 行业 RSI 情绪 Tab */}
        {activeTab === 'panic' && (
          <div className="space-y-4">
            <p className="text-gray-500 max-w-2xl leading-relaxed font-medium text-sm">
              基于各 GICS 行业代表性 ETF 的 RSI(14) 衡量价格动量强弱：
              <code className="mx-1 px-1.5 py-0.5 bg-gray-100 rounded text-xs font-mono">RSI &lt; 30</code>
              超卖（弱势）；
              <code className="mx-1 px-1.5 py-0.5 bg-gray-100 rounded text-xs font-mono">RSI &gt; 70</code>
              超买（强势）。
            </p>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              <span className="text-xs text-gray-400 font-bold uppercase tracking-widest">
                数据来源：SPDR 行业 ETF 日线 · 每小时缓存
              </span>
            </div>

            {loading && (
              <div className="flex items-center justify-center h-64">
                <Spinner size={40} />
              </div>
            )}

            {error && !loading && (
              <div className="p-6 bg-red-50 border border-red-200 rounded-xl flex items-start justify-between gap-4">
                <p className="text-red-600 text-sm font-medium">{error}</p>
                <button
                  onClick={loadData}
                  className="shrink-0 text-xs font-semibold text-red-700 border border-red-300 rounded-lg px-3 py-1.5 hover:bg-red-100 transition-colors"
                >
                  重试
                </button>
              </div>
            )}

            {data && !loading && (
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* 左侧：行业 RSI 排行（低→高） */}
                <div className="lg:col-span-1">
                  <div className="bg-white/80 backdrop-blur-md rounded-2xl border border-gray-100 shadow-sm p-5">
                    <div className="text-sm font-bold text-gray-700 mb-4 flex items-center justify-between">
                      <span>行业 RSI 排行</span>
                      <span className="text-xs text-gray-400 font-normal">截至 {data.as_of}</span>
                    </div>
                    <SectorPanicBar
                      sectors={data.sectors}
                      selectedSymbol={selected?.symbol ?? ''}
                      onSelect={setSelected}
                    />
                  </div>
                </div>

                {/* 右侧：历史 RSI 走势图 */}
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
                            {selected.symbol} · 历史 RSI(14) 走势（近 1 年日线）
                          </div>
                        </div>
                        <div className="text-right">
                          <div
                            className="text-3xl font-bold tabular-nums"
                            style={{ color: currentColor }}
                          >
                            {currentRsi.toFixed(1)}
                          </div>
                          <div className="text-xs text-gray-400 font-mono mt-0.5">RSI(14)</div>
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
                        <span>RSI &lt; 30 → <span className="text-red-500 font-bold">超卖（弱势）</span></span>
                        <span>RSI = 50 → <span className="text-yellow-600 font-bold">中性</span></span>
                        <span>RSI &gt; 70 → <span className="text-blue-500 font-bold">超买（强势）</span></span>
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
                      <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1">
                        <span><span className="text-red-500 font-bold">&lt; 30</span> 超卖</span>
                        <span><span className="text-orange-500 font-bold">30-45</span> 偏弱</span>
                        <span><span className="text-yellow-600 font-bold">45-55</span> 中性</span>
                        <span><span className="text-blue-500 font-bold">55-70</span> 偏强</span>
                        <span><span className="text-blue-700 font-bold">&gt; 70</span> 超买</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 行业估值分析 Tab */}
        {activeTab === 'valuation' && (
          <div>
            <SectorValuationGrid />

            {/* 计算方法说明卡片（图表下方） */}
            <div className="mt-4 p-4 bg-slate-50 border border-slate-200 rounded-xl text-sm">
              <div className="font-semibold text-slate-700 mb-3">计算方法（PE z-score）</div>
              <div className="space-y-2 text-slate-600">
                <div>
                  <span className="font-medium text-slate-800">1. 数据采集</span>
                  ：从 FMP 拉取 GICS 各行业近 5 年（约 20 个季度）的季度末市盈率（PE）历史序列。
                </div>
                <div>
                  <span className="font-medium text-slate-800">2. 标准化公式</span>
                  ：
                  <code className="mx-1.5 px-2 py-0.5 bg-white border border-slate-200 rounded text-xs font-mono text-slate-700">
                    z-score = (当前 PE − 历史均值 μ) / 历史标准差 σ
                  </code>
                </div>
                <div>
                  <span className="font-medium text-slate-800">3. 热度分级</span>
                  ：根据 z-score 落入的标准差区间判断估值冷热——
                  <span className="text-blue-700 font-medium"> z ≤ −2σ</span> 极度低估 ·
                  <span className="text-blue-500 font-medium"> −2σ ~ −1σ</span> 低估 ·
                  <span className="text-slate-500 font-medium"> −1σ ~ +1σ</span> 中性 ·
                  <span className="text-orange-500 font-medium"> +1σ ~ +2σ</span> 高估 ·
                  <span className="text-red-500 font-medium"> z ≥ +2σ</span> 极度高估
                </div>
              </div>

              {/* 示例 */}
              <div className="mt-3 p-3 bg-white border border-slate-100 rounded-lg">
                <div className="text-xs font-semibold text-slate-600 mb-2">示例：信息技术行业</div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                  <div className="space-y-0.5">
                    <div className="text-slate-400">历史均值 μ（5年）</div>
                    <div className="font-mono font-bold text-slate-700">28.00</div>
                  </div>
                  <div className="space-y-0.5">
                    <div className="text-slate-400">历史标准差 σ</div>
                    <div className="font-mono font-bold text-slate-700">4.20</div>
                  </div>
                  <div className="space-y-0.5">
                    <div className="text-slate-400">当前 PE</div>
                    <div className="font-mono font-bold text-slate-700">35.00</div>
                  </div>
                </div>
                <div className="mt-2 text-xs text-slate-500 border-t border-slate-50 pt-2">
                  z-score = (35.00 − 28.00) / 4.20 ≈{' '}
                  <span className="font-bold font-mono text-orange-500">+1.67</span>
                  <span className="ml-2">→ 落在 [+1σ, +2σ) 区间 →</span>
                  <span className="ml-1 font-semibold text-orange-500">高估</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardShell>
  )
}
