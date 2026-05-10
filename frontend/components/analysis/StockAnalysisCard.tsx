'use client'

import { AnalysisResponse } from '@/lib/api/analysis'
import { ExternalLink, ShieldCheck, Info, BarChart3, Clock, Target, TrendingUp } from 'lucide-react'

interface StockAnalysisCardProps {
  analysis: AnalysisResponse
}

const LAYER_DISPLAY_NAMES: Record<string, string> = {
  financial: '财务健康',
  industry: '行业前景',
  company: '公司质量',
  competition: '竞争格局',
  trading: '交易估值',
  expectation: '市场预期',
}

const LAYER_COLORS: Record<string, string> = {
  financial: 'from-blue-500 to-blue-600',
  industry: 'from-purple-500 to-purple-600',
  company: 'from-green-500 to-green-600',
  competition: 'from-orange-500 to-orange-600',
  trading: 'from-red-500 to-red-600',
  expectation: 'from-yellow-500 to-yellow-600',
}

export default function StockAnalysisCard({ analysis }: StockAnalysisCardProps) {
  const getRecommendationColor = (rec: string) => {
    switch (rec) {
      case 'BUY':
        return 'bg-green-500 text-white shadow-lg shadow-green-200'
      case 'HOLD':
        return 'bg-yellow-500 text-white shadow-lg shadow-yellow-200'
      case 'SELL':
        return 'bg-red-500 text-white shadow-lg shadow-red-200'
      default:
        return 'bg-gray-500 text-white shadow-lg shadow-gray-200'
    }
  }

  return (
    <div className="bg-white rounded-2xl shadow-xl shadow-gray-200/50 border border-gray-100 overflow-hidden animate-in fade-in zoom-in-95 duration-500">
      {/* Header */}
      <div className="px-8 py-6 bg-gradient-to-br from-blue-600 via-blue-700 to-indigo-800 text-white relative">
        <div className="absolute top-0 right-0 p-8 opacity-10">
          <TrendingUp className="w-24 h-24" />
        </div>
        <div className="flex items-center justify-between relative z-10">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 bg-white/20 backdrop-blur-md rounded-2xl flex items-center justify-center text-3xl font-black border border-white/20">
              {analysis.ticker.slice(0, 1)}
            </div>
            <div>
              <h2 className="text-2xl font-black tracking-tight">{analysis.company_name}</h2>
              <div className="flex items-center gap-2 mt-1">
                <span className="px-2 py-0.5 bg-white/20 rounded text-xs font-bold tracking-widest">{analysis.ticker}</span>
                <span className="w-1 h-1 rounded-full bg-blue-300" />
                <span className="text-sm text-blue-100 font-medium">智能投资分析报告</span>
              </div>
            </div>
          </div>
          <div className="text-right flex flex-col items-end">
            <div className="flex items-baseline gap-1">
              <span className="text-5xl font-black tracking-tighter">{analysis.final_score.toFixed(1)}</span>
              <span className="text-blue-200 text-sm font-bold opacity-70">/ 100</span>
            </div>
            <span className={`inline-block mt-3 px-4 py-1.5 rounded-xl text-xs font-black uppercase tracking-widest ${getRecommendationColor(analysis.recommendation)}`}>
              {analysis.recommendation}
            </span>
          </div>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="px-8 py-6 grid grid-cols-1 md:grid-cols-3 gap-6 bg-gray-50/50 border-b border-gray-100">
        <div className="flex items-center gap-4 bg-white p-4 rounded-2xl border border-gray-100 shadow-sm">
          <div className="w-10 h-10 rounded-xl bg-indigo-50 flex items-center justify-center text-indigo-600">
            <Target className="w-5 h-5" />
          </div>
          <div>
            <p className="text-[10px] text-gray-400 font-bold uppercase tracking-wider">风险/回报</p>
            <p className="text-lg font-black text-gray-900">{analysis.risk_reward_ratio.toFixed(2)}</p>
          </div>
        </div>
        <div className="flex items-center gap-4 bg-white p-4 rounded-2xl border border-gray-100 shadow-sm">
          <div className="w-10 h-10 rounded-xl bg-emerald-50 flex items-center justify-center text-emerald-600">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <p className="text-[10px] text-gray-400 font-bold uppercase tracking-wider">建议仓位</p>
            <p className="text-sm font-bold text-gray-900">{analysis.position_recommendation}</p>
          </div>
        </div>
        <div className="flex items-center gap-4 bg-white p-4 rounded-2xl border border-gray-100 shadow-sm">
          <div className="w-10 h-10 rounded-xl bg-orange-50 flex items-center justify-center text-orange-600">
            <Clock className="w-5 h-5" />
          </div>
          <div>
            <p className="text-[10px] text-gray-400 font-bold uppercase tracking-wider">分析耗时</p>
            <p className="text-sm font-bold text-gray-900">
              {analysis.analysis_duration_seconds ? `${analysis.analysis_duration_seconds.toFixed(2)}s` : 'N/A'}
            </p>
          </div>
        </div>
      </div>

      {/* Layers */}
      <div className="px-8 py-8">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-black text-gray-800 flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-blue-600" />
            六层深度分析
          </h3>
          <div className="h-px flex-1 mx-4 bg-gray-100" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {Object.entries(analysis.layers).map(([key, layer]) => {
            const colorClass = LAYER_COLORS[key] || 'from-gray-500 to-gray-600'
            return (
              <div
                key={key}
                className="group bg-white rounded-2xl p-5 border border-gray-100 hover:border-blue-200 hover:shadow-xl hover:shadow-blue-50 transition-all duration-300 relative overflow-hidden"
              >
                <div className="flex items-center justify-between mb-4 relative z-10">
                  <span className="text-sm font-black text-gray-700">
                    {LAYER_DISPLAY_NAMES[key] || key}
                  </span>
                  <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${colorClass} flex items-center justify-center shadow-lg shadow-blue-100 group-hover:scale-110 transition-transform`}>
                    <span className="text-white text-sm font-black">{layer.score.toFixed(0)}</span>
                  </div>
                </div>
                <p className="text-xs text-gray-500 leading-relaxed mb-4 line-clamp-3 group-hover:text-gray-600">{layer.summary}</p>
                {layer.key_findings.length > 0 && (
                  <div className="space-y-2 mb-4">
                    {layer.key_findings.slice(0, 2).map((finding, i) => (
                      <div key={i} className="flex items-start gap-2">
                        <div className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-1 flex-shrink-0" />
                        <p className="text-[11px] text-gray-600 font-medium leading-tight">{finding}</p>
                      </div>
                    ))}
                  </div>
                )}
                <div className="flex items-center justify-between pt-4 border-t border-gray-50 text-[10px] font-bold">
                  <span className="text-gray-400 uppercase tracking-widest">Confidence</span>
                  <div className="flex items-center gap-2">
                    <div className="w-12 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full bg-blue-500" style={{ width: `${layer.confidence * 100}%` }} />
                    </div>
                    <span className="text-blue-600">{(layer.confidence * 100).toFixed(0)}%</span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Sources */}
      {analysis.sources.length > 0 && (
        <div className="px-8 py-6 bg-gray-50/50 border-t border-gray-100">
          <div className="flex items-center gap-3 mb-4">
            <Info className="w-4 h-4 text-gray-400" />
            <h3 className="text-xs font-black text-gray-400 uppercase tracking-[0.2em]">底层数据源</h3>
          </div>
          <div className="flex flex-wrap gap-2">
            {analysis.sources.slice(0, 12).map((source, i) => (
              <a
                key={i}
                href={source.url || '#'}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-gray-200 rounded-lg text-[11px] font-bold text-gray-600 hover:text-blue-600 hover:border-blue-200 hover:shadow-sm transition-all"
              >
                {source.source}
                <ExternalLink className="w-3 h-3 opacity-30" />
              </a>
            ))}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="px-8 py-4 bg-gray-100/50 flex justify-between items-center text-[10px] font-bold text-gray-400 uppercase tracking-widest">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
          报告生成时间: {new Date(analysis.analysis_timestamp).toLocaleString('zh-CN')}
        </div>
        <div>© DEEPALPHA AI RESEARCH</div>
      </div>
    </div>
  )
}