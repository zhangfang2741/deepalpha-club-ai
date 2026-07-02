'use client'

import { useState, useCallback } from 'react'
import { fetchIchimokuAnalysis, type IchimokuAnalysisResult } from '@/lib/api/ichimoku'
import { IchimokuChart } from '@/components/ichimoku/IchimokuChart'
import { SignalPanel } from '@/components/ichimoku/SignalPanel'
import { ConceptGuide } from '@/components/ichimoku/ConceptGuide'
import DashboardShell from '@/components/layout/DashboardShell'

const DEFAULT_SYMBOL = 'AAPL'
const TODAY = new Date().toISOString().split('T')[0]
// 云需 52+26 根数据，日线默认放宽到 1 年
const ONE_YEAR_AGO = new Date(Date.now() - 365 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
const THREE_YEARS_AGO = new Date(Date.now() - 3 * 365 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]

function DateInput({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-slate-400">{label}</label>
      <input
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
    </div>
  )
}

export default function IchimokuPage() {
  const [symbol, setSymbol] = useState(DEFAULT_SYMBOL)
  const [startDate, setStartDate] = useState(ONE_YEAR_AGO)
  const [endDate, setEndDate] = useState(TODAY)
  const [freq, setFreq] = useState<'daily' | 'weekly'>('daily')
  const [displacement, setDisplacement] = useState<26 | 25>(26)
  const [result, setResult] = useState<IchimokuAnalysisResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [showTenkan, setShowTenkan] = useState(true)
  const [showKijun, setShowKijun] = useState(true)
  const [showCloud, setShowCloud] = useState(true)
  const [showChikou, setShowChikou] = useState(true)
  const [showSignals, setShowSignals] = useState(true)

  const handleFreqChange = (next: 'daily' | 'weekly') => {
    setFreq(next)
    if (next === 'weekly' && startDate > THREE_YEARS_AGO) setStartDate(THREE_YEARS_AGO)
  }

  const handleAnalyze = useCallback(async () => {
    if (!symbol.trim()) return
    setLoading(true)
    setError(null)
    try {
      const data = await fetchIchimokuAnalysis(symbol.trim().toUpperCase(), startDate, endDate, freq, displacement)
      setResult(data)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '分析失败，请检查股票代码或日期范围'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [symbol, startDate, endDate, freq, displacement])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleAnalyze()
  }

  return (
    <DashboardShell>
      <div className="flex flex-col gap-4 lg:h-full">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-bold text-slate-100">一目均衡表</h1>
          <p className="text-sm text-slate-400">
            基于 Ichimoku Kinko Hyo 云图，自动计算转换线、基准线、先行带 A/B（云）、迟行线，识别 TK 交叉与云突破，综合三役给出操作建议
          </p>
        </div>

        <div className="flex flex-wrap items-end gap-3 bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-slate-400">股票代码</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="如 AAPL、NVDA"
              className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 w-32 focus:outline-none focus:ring-2 focus:ring-blue-500 uppercase"
            />
          </div>
          <DateInput label="起始日期" value={startDate} onChange={setStartDate} />
          <DateInput label="结束日期" value={endDate} onChange={setEndDate} />
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-slate-400">周期</label>
            <select
              value={freq}
              onChange={(e) => handleFreqChange(e.target.value as 'daily' | 'weekly')}
              className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="daily">日线</option>
              <option value="weekly">周线</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-slate-400">平移约定</label>
            <select
              value={displacement}
              onChange={(e) => setDisplacement(Number(e.target.value) as 26 | 25)}
              className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value={26}>经典 (26)</option>
              <option value={25}>TradingView (25)</option>
            </select>
          </div>

          <button
            onClick={handleAnalyze}
            disabled={loading}
            className="w-full sm:w-auto px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-400 text-white text-sm font-semibold transition-colors"
          >
            {loading ? '分析中...' : '开始分析'}
          </button>

          <div className="flex flex-wrap items-center gap-3 w-full lg:w-auto lg:ml-2 lg:border-l lg:border-slate-700 lg:pl-3">
            {[
              { key: 'tenkan', label: '转换线', value: showTenkan, set: setShowTenkan },
              { key: 'kijun', label: '基准线', value: showKijun, set: setShowKijun },
              { key: 'cloud', label: '云', value: showCloud, set: setShowCloud },
              { key: 'chikou', label: '迟行线', value: showChikou, set: setShowChikou },
              { key: 'signals', label: '信号', value: showSignals, set: setShowSignals },
            ].map(({ key, label, value, set }) => (
              <label key={key} className="flex items-center gap-1.5 cursor-pointer text-xs text-slate-400">
                <input
                  type="checkbox"
                  checked={value}
                  onChange={(e) => set(e.target.checked)}
                  className="accent-blue-500"
                />
                {label}
              </label>
            ))}
          </div>
        </div>

        <ConceptGuide />

        {error && (
          <div className="bg-red-950/40 border border-red-800 rounded-lg px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {loading && (
          <div className="flex-1 min-h-[50vh] flex items-center justify-center text-slate-400">
            <div className="flex flex-col items-center gap-3">
              <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              <span className="text-sm">正在运行一目均衡表分析，请稍候...</span>
            </div>
          </div>
        )}

        {!loading && !result && !error && (
          <div className="flex-1 min-h-[50vh] flex items-center justify-center text-slate-500">
            <div className="text-center">
              <div className="text-4xl mb-3">☁️</div>
              <p className="text-sm">输入股票代码，点击「开始分析」运行一目均衡表</p>
              <p className="text-xs mt-1 text-slate-600">支持美股（AAPL）及 A 股（SH600519），建议至少 1 年数据以形成完整云层</p>
            </div>
          </div>
        )}

        {!loading && result && (
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4 lg:flex-1 lg:min-h-0">
            <div className="h-[70vh] lg:h-auto min-h-0 rounded-xl overflow-hidden bg-slate-900 border border-slate-800 p-3">
              <IchimokuChart
                data={result}
                showTenkan={showTenkan}
                showKijun={showKijun}
                showCloud={showCloud}
                showChikou={showChikou}
                showSignals={showSignals}
              />
            </div>

            <div className="min-h-0 rounded-xl bg-slate-900 border border-slate-800 p-3 lg:overflow-y-auto">
              <SignalPanel data={result} />
            </div>
          </div>
        )}
      </div>
    </DashboardShell>
  )
}
