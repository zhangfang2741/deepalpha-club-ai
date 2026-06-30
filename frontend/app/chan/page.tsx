'use client'

import { useState, useCallback } from 'react'
import { fetchChanAnalysis, type ChanAnalysisResult } from '@/lib/api/chan'
import { ChanChart } from '@/components/chan/ChanChart'
import { SignalPanel } from '@/components/chan/SignalPanel'
import { ConceptGuide } from '@/components/chan/ConceptGuide'
import DashboardShell from '@/components/layout/DashboardShell'

const DEFAULT_SYMBOL = 'AAPL'
const TODAY = new Date().toISOString().split('T')[0]
const SIX_MONTHS_AGO = new Date(Date.now() - 180 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
const TWO_YEARS_AGO = new Date(Date.now() - 730 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]

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

export default function ChanPage() {
  const [symbol, setSymbol] = useState(DEFAULT_SYMBOL)
  const [startDate, setStartDate] = useState(SIX_MONTHS_AGO)
  const [endDate, setEndDate] = useState(TODAY)
  const [freq, setFreq] = useState<'daily' | 'weekly'>('daily')
  const [result, setResult] = useState<ChanAnalysisResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 显示选项
  const [showStrokes, setShowStrokes] = useState(true)
  const [showSegments, setShowSegments] = useState(true)
  const [showPivots, setShowPivots] = useState(true)
  const [showSignals, setShowSignals] = useState(true)
  const [showMacd, setShowMacd] = useState(true)

  // 切换周期：周线需要更长区间才能识别出结构，自动放宽起始日期
  const handleFreqChange = (next: 'daily' | 'weekly') => {
    setFreq(next)
    if (next === 'weekly' && startDate > TWO_YEARS_AGO) setStartDate(TWO_YEARS_AGO)
  }

  const handleAnalyze = useCallback(async () => {
    if (!symbol.trim()) return
    setLoading(true)
    setError(null)
    try {
      const data = await fetchChanAnalysis(symbol.trim().toUpperCase(), startDate, endDate, freq)
      setResult(data)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '分析失败，请检查股票代码或日期范围'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [symbol, startDate, endDate, freq])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleAnalyze()
  }

  return (
    <DashboardShell>
      <div className="flex flex-col h-full gap-4">
        {/* 标题 + 控制栏 */}
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-bold text-slate-100">缠论技术分析</h1>
          <p className="text-sm text-slate-400">
            基于缠中说禅理论，自动识别分型、笔、线段、中枢，判断背驰，生成三类买卖点
          </p>
        </div>

        {/* 参数输入 */}
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

          <button
            onClick={handleAnalyze}
            disabled={loading}
            className="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-400 text-white text-sm font-semibold transition-colors"
          >
            {loading ? '分析中...' : '开始分析'}
          </button>

          {/* 显示开关 */}
          <div className="flex items-center gap-3 ml-2 border-l border-slate-700 pl-3">
            {[
              { key: 'strokes', label: '笔', value: showStrokes, set: setShowStrokes },
              { key: 'segments', label: '线段', value: showSegments, set: setShowSegments },
              { key: 'pivots', label: '中枢', value: showPivots, set: setShowPivots },
              { key: 'signals', label: '信号', value: showSignals, set: setShowSignals },
              { key: 'macd', label: 'MACD', value: showMacd, set: setShowMacd },
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

        {/* 缠论概念科普 */}
        <ConceptGuide />

        {/* 错误提示 */}
        {error && (
          <div className="bg-red-950/40 border border-red-800 rounded-lg px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* 加载状态 */}
        {loading && (
          <div className="flex-1 flex items-center justify-center text-slate-400">
            <div className="flex flex-col items-center gap-3">
              <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              <span className="text-sm">正在运行缠论分析，请稍候...</span>
            </div>
          </div>
        )}

        {/* 初始状态 */}
        {!loading && !result && !error && (
          <div className="flex-1 flex items-center justify-center text-slate-500">
            <div className="text-center">
              <div className="text-4xl mb-3">📈</div>
              <p className="text-sm">输入股票代码，点击「开始分析」运行缠论</p>
              <p className="text-xs mt-1 text-slate-600">支持美股（AAPL）及 A 股（SH600519）</p>
            </div>
          </div>
        )}

        {/* 主内容区 */}
        {!loading && result && (
          <div className="flex-1 grid grid-cols-[1fr_320px] gap-4 min-h-0">
            {/* 图表 */}
            <div className="min-h-0 rounded-xl overflow-hidden bg-slate-900 border border-slate-800 p-3">
              <ChanChart
                data={result}
                showStrokes={showStrokes}
                showSegments={showSegments}
                showPivots={showPivots}
                showSignals={showSignals}
                showMacd={showMacd}
              />
            </div>

            {/* 信号面板 */}
            <div className="min-h-0 rounded-xl bg-slate-900 border border-slate-800 p-3 overflow-y-auto">
              <SignalPanel data={result} />
            </div>
          </div>
        )}
      </div>
    </DashboardShell>
  )
}
