'use client'

import { useState } from 'react'
import { analyzeStock, AnalysisResponse } from '@/lib/api/analysis'
import StockAnalysisCard from '@/components/analysis/StockAnalysisCard'
import { LineChart, TrendingUp, Search, Info } from 'lucide-react'
import DashboardShell from '@/components/layout/DashboardShell'

export default function AnalysisPage() {
  const [ticker, setTicker] = useState('')
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleAnalyze = async () => {
    if (!ticker.trim()) {
      setError('请输入股票代码')
      return
    }

    setLoading(true)
    setError(null)
    setAnalysis(null)

    try {
      const result = await analyzeStock(ticker.trim().toUpperCase())
      setAnalysis(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : '分析失败')
    } finally {
      setLoading(false)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleAnalyze()
    }
  }

  return (
    <DashboardShell>
      <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
      {/* Header */}
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-extrabold text-gray-900 tracking-tight">
          投资评分分析
        </h1>
        <p className="text-gray-500 max-w-2xl leading-relaxed">
          基于六层分析框架的股票投资评分系统，深度解析 SEC EDGAR、FMP 财务数据及市场情绪，为您提供专业的投资参考。
        </p>
      </div>

      {/* Search Form */}
      <div className="bg-white/80 backdrop-blur-md rounded-2xl shadow-sm border border-blue-100 p-8">
        <div className="flex flex-col md:flex-row gap-6">
          <div className="flex-1">
            <label htmlFor="ticker" className="block text-sm font-semibold text-gray-700 mb-2 ml-1">
              股票代码
            </label>
            <div className="relative group">
              <div className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 group-focus-within:text-blue-500 transition-colors">
                <Search className="w-5 h-5" />
              </div>
              <input
                type="text"
                id="ticker"
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                onKeyPress={handleKeyPress}
                placeholder="输入代码, 如 NVDA"
                className="w-full pl-12 pr-5 py-3.5 bg-gray-50/50 border border-gray-200 rounded-xl focus:ring-4 focus:ring-blue-500/10 focus:border-blue-500 outline-none transition-all text-lg font-medium placeholder:text-gray-400"
              />
            </div>
          </div>
          <div className="flex items-end">
            <button
              onClick={handleAnalyze}
              disabled={loading}
              className="w-full md:w-auto px-8 py-4 bg-blue-600 text-white rounded-xl font-bold shadow-lg shadow-blue-200 hover:bg-blue-700 hover:shadow-blue-300 active:scale-95 disabled:bg-blue-300 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2 min-w-[160px]"
            >
              {loading ? (
                <>
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  分析中...
                </>
              ) : (
                <>
                  <LineChart className="w-5 h-5" />
                  开始分析
                </>
              )}
            </button>
          </div>
        </div>

        {error && (
          <div className="mt-6 p-4 bg-red-50 border border-red-100 rounded-xl text-red-700 flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-red-500" />
            <span className="text-sm font-medium">{error}</span>
          </div>
        )}
      </div>

      {/* Popular Stocks */}
      <div className="bg-white/60 backdrop-blur-sm rounded-2xl shadow-sm border border-gray-100 p-6">
        <h3 className="text-sm font-semibold text-gray-600 mb-4 flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-blue-500" />
          热门查询
        </h3>
        <div className="flex flex-wrap gap-3">
          {['NVDA', 'AAPL', 'MSFT', 'GOOGL', 'META', 'TSLA', 'AMZN', 'AMD'].map((stock) => (
            <button
              key={stock}
              onClick={() => setTicker(stock)}
              className="px-5 py-2.5 bg-white text-gray-700 rounded-xl hover:bg-blue-600 hover:text-white transition-all text-sm font-bold border border-gray-100 hover:border-blue-600 shadow-sm"
            >
              {stock}
            </button>
          ))}
        </div>
      </div>

      {/* Analysis Result */}
      {analysis && (
        <div className="animate-in fade-in duration-300">
          <StockAnalysisCard analysis={analysis} />
        </div>
      )}

      {/* Info */}
      {!analysis && !loading && !error && (
        <div className="bg-blue-600 rounded-2xl shadow-xl shadow-blue-100 border border-blue-500 p-8 text-white relative overflow-hidden">
          <div className="absolute top-0 right-0 p-8 opacity-10">
            <Info className="w-32 h-32" />
          </div>
          <h3 className="text-lg font-bold mb-6 flex items-center gap-2 relative">
            <div className="w-6 h-6 bg-white/20 rounded-full flex items-center justify-center text-xs">
              ?
            </div>
            六层分析框架说明
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 relative">
            {[
              { n: '1', title: '企业质量', desc: '管理层、护城河、品牌影响力' },
              { n: '2', title: '财务健康', desc: '收入、利润、自由现金流状况' },
              { n: '3', title: '行业前景', desc: '赛道增速、宏观趋势、竞争格局' },
              { n: '4', title: '市场预期', desc: '市场情绪、估值倍数、预期差' },
              { n: '5', title: '竞争格局', desc: '市场份额、进入壁垒、定价权' },
              { n: '6', title: '交易估值', desc: 'PE、PB、EV/EBITDA 历史水位' },
            ].map((item) => (
              <div key={item.n} className="bg-white/10 backdrop-blur-sm rounded-xl p-4 border border-white/10 hover:bg-white/20 transition-colors">
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-blue-200 font-black italic text-xl">0{item.n}</span>
                  <p className="font-bold text-base">{item.title}</p>
                </div>
                <p className="text-sm text-blue-100 leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      )}
      </div>
    </DashboardShell>
  )
}