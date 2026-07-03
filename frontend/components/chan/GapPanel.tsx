'use client'
import { useState, useCallback } from 'react'
import {
  fetchStructureGap,
  type StructureGapResult,
  type GapItem,
  type GapDirection,
} from '@/lib/api/chan'

interface Props {
  symbol: string
  startDate: string
  endDate: string
  freq: 'daily' | 'weekly'
}

const DIRECTION_STYLE: Record<
  GapDirection,
  { label: string; bg: string; border: string; text: string; dot: string }
> = {
  price_lags_industry: {
    label: '技术面滞后于产业 · 潜在机会',
    bg: 'bg-green-950/30',
    border: 'border-green-800/60',
    text: 'text-green-400',
    dot: 'bg-green-400',
  },
  price_ahead_of_fundamentals: {
    label: '价格领先于基本面 · 潜在风险',
    bg: 'bg-red-950/30',
    border: 'border-red-800/60',
    text: 'text-red-400',
    dot: 'bg-red-400',
  },
  unclear: {
    label: '方向不明 · 信息不足',
    bg: 'bg-slate-800/50',
    border: 'border-slate-700',
    text: 'text-slate-300',
    dot: 'bg-slate-400',
  },
}

function GapCard({ gap }: { gap: GapItem }) {
  const s = DIRECTION_STYLE[gap.direction] ?? DIRECTION_STYLE.unclear
  return (
    <div className={`rounded-lg border p-3 ${s.bg} ${s.border}`}>
      <div className="flex items-center gap-2 mb-2">
        <span className={`inline-block w-2 h-2 rounded-full ${s.dot}`} />
        <span className="text-sm font-bold text-slate-200">{gap.dimension}</span>
        <span className={`text-[11px] ${s.text}`}>{s.label}</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-2">
        <div className="text-xs">
          <div className="text-slate-500 mb-0.5">技术面</div>
          <div className="text-slate-300">{gap.market_says}</div>
        </div>
        <div className="text-xs">
          <div className="text-slate-500 mb-0.5">产业面</div>
          <div className="text-slate-300">{gap.industry_says}</div>
        </div>
      </div>
      <div className="text-xs text-slate-400 border-t border-slate-700/50 pt-2">
        <span className="text-slate-500">可能含义：</span>
        {gap.interpretation}
      </div>
    </div>
  )
}

export function GapPanel({ symbol, startDate, endDate, freq }: Props) {
  const [industryView, setIndustryView] = useState('')
  const [result, setResult] = useState<StructureGapResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleRun = useCallback(async () => {
    if (!industryView.trim() || !symbol.trim()) return
    setLoading(true)
    setError(null)
    try {
      const data = await fetchStructureGap(
        symbol.trim().toUpperCase(),
        startDate,
        endDate,
        industryView.trim(),
        freq,
      )
      setResult(data)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '分析失败，请稍后再试'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [industryView, symbol, startDate, endDate, freq])

  return (
    <div className="rounded-xl bg-slate-900 border border-slate-800 p-4 flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <h2 className="text-lg font-semibold text-slate-100">市场结构 × 产业结构 GAP 分析</h2>
        <p className="text-xs text-slate-400">
          输入你对该标的的产业判断，系统把它与当前技术面结构并置，重点找出二者的背离——
          不预测涨跌，只发现值得研究的矛盾。
        </p>
      </div>

      <textarea
        value={industryView}
        onChange={(e) => setIndustryView(e.target.value)}
        rows={4}
        placeholder="你对该公司/行业产业结构的判断，例如：所处产业链位置、景气周期、竞争格局、需求趋势、成本变化、订单/库存拐点……"
        className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 resize-y focus:outline-none focus:ring-2 focus:ring-blue-500"
      />

      <div className="flex items-center gap-3">
        <button
          onClick={handleRun}
          disabled={loading || !industryView.trim()}
          className="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-400 text-white text-sm font-semibold transition-colors"
        >
          {loading ? '分析中...' : '找出 GAP'}
        </button>
        <span className="text-xs text-slate-500">基于 {symbol.toUpperCase()} 当前技术面结构</span>
      </div>

      {error && (
        <div className="bg-red-950/40 border border-red-800 rounded-lg px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center gap-3 py-6 text-slate-400">
          <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-sm">正在并置技术面与产业面，寻找背离...</span>
        </div>
      )}

      {!loading && result && (
        <div className="flex flex-col gap-3">
          {/* 背离（重点） */}
          <div>
            <div className="text-xs font-semibold text-slate-400 mb-2">🔍 背离（重点）</div>
            {result.gaps.length > 0 ? (
              <div className="flex flex-col gap-2">
                {result.gaps.map((g, i) => (
                  <GapCard key={i} gap={g} />
                ))}
              </div>
            ) : (
              <div className="text-sm text-slate-400 bg-slate-800/40 rounded-lg p-3">
                未发现明显背离——技术面与产业面大体一致（多已被市场定价）。
              </div>
            )}
          </div>

          {/* 一致处 */}
          {result.aligned.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-slate-400 mb-2">✅ 一致处（多已定价，略过）</div>
              <ul className="flex flex-col gap-1">
                {result.aligned.map((a, i) => (
                  <li key={i} className="text-xs text-slate-300 flex gap-1.5">
                    <span className="text-slate-500 shrink-0">·</span>
                    <span>{a}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 关键问题 */}
          {result.key_question && (
            <div className="rounded-lg border border-blue-900/50 bg-blue-950/20 p-3">
              <div className="text-xs font-semibold text-blue-300 mb-1">❓ 最值得研究的问题</div>
              <div className="text-sm text-slate-200">{result.key_question}</div>
            </div>
          )}

          {/* 诚实边界 */}
          {result.caveats.length > 0 && (
            <div className="text-[11px] text-slate-500 leading-relaxed border-t border-slate-800 pt-2">
              {result.caveats.join('；')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
