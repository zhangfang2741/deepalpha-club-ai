'use client'
import { useState, useCallback, useMemo, useEffect, useRef } from 'react'
import {
  submitStructureGap,
  getStructureGapStatus,
  type StructureGapResult,
  type GapItem,
  type GapDirection,
} from '@/lib/api/chan'

const POLL_INTERVAL = 2500 // 轮询间隔
const MAX_WAIT = 120000 // 最长等待，超时提示重试

interface Props {
  symbol: string
  startDate: string
  endDate: string
  freq: 'daily' | 'weekly'
}

// 快选维度：点一下即可给出产业判断的骨架，值直接对应 gap 的比对维度
const DIMENSIONS: { key: string; label: string; options: string[] }[] = [
  { key: '景气周期', label: '景气周期', options: ['加速上行', '见顶', '下行', '见底回升'] },
  { key: '需求趋势', label: '需求趋势', options: ['转强', '平稳', '转弱'] },
  { key: '竞争格局', label: '竞争格局', options: ['改善', '稳定', '恶化'] },
  { key: '成本·毛利', label: '成本·毛利', options: ['改善', '平稳', '承压'] },
  { key: '相对基本面估值', label: '相对估值', options: ['低估', '合理', '高估'] },
]

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
  const [picks, setPicks] = useState<Record<string, string>>({})
  const [extra, setExtra] = useState('')
  const [result, setResult] = useState<StructureGapResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 点击 chip：未选则选中，已选再点则取消（toggle）
  const togglePick = (key: string, option: string) => {
    setPicks((prev) => {
      const next = { ...prev }
      if (next[key] === option) delete next[key]
      else next[key] = option
      return next
    })
  }

  // 把快选骨架 + 补充文本拼成发给后端的 industry_view
  const composedView = useMemo(() => {
    const struct = DIMENSIONS.filter((d) => picks[d.key])
      .map((d) => `${d.key}：${picks[d.key]}`)
      .join('；')
    const text = extra.trim()
    return [struct, text ? `补充：${text}` : ''].filter(Boolean).join('\n')
  }, [picks, extra])

  const canRun = composedView.length > 0 && symbol.trim().length > 0

  // 轮询定时器与取消标记：组件卸载或重新提交时清理，避免残留轮询
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const cancelledRef = useRef(false)

  useEffect(() => {
    return () => {
      cancelledRef.current = true
      if (pollRef.current) clearTimeout(pollRef.current)
    }
  }, [])

  const handleRun = useCallback(async () => {
    if (!canRun) return
    // 复位上一次可能仍在进行的轮询
    cancelledRef.current = false
    if (pollRef.current) clearTimeout(pollRef.current)
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const job = await submitStructureGap(
        symbol.trim().toUpperCase(),
        startDate,
        endDate,
        composedView,
        freq,
      )
      const startTs = Date.now()

      const poll = async () => {
        if (cancelledRef.current) return
        try {
          const st = await getStructureGapStatus(job.job_id)
          if (cancelledRef.current) return
          if (st.status === 'done' && st.result) {
            setResult(st.result)
            setLoading(false)
            return
          }
          if (st.status === 'failed') {
            setError(st.error || '分析失败，请稍后再试')
            setLoading(false)
            return
          }
          if (Date.now() - startTs > MAX_WAIT) {
            setError('分析超时，请稍后重试')
            setLoading(false)
            return
          }
          pollRef.current = setTimeout(poll, POLL_INTERVAL)
        } catch (err: unknown) {
          if (cancelledRef.current) return
          setError(err instanceof Error ? err.message : '获取结果失败，请稍后重试')
          setLoading(false)
        }
      }

      pollRef.current = setTimeout(poll, 2000)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '提交失败，请稍后再试'
      setError(msg)
      setLoading(false)
    }
  }, [canRun, composedView, symbol, startDate, endDate, freq])

  return (
    <div className="rounded-xl bg-slate-900 border border-slate-800 p-4 flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <h2 className="text-lg font-semibold text-slate-100">市场结构 × 产业结构 GAP 分析</h2>
        <p className="text-xs text-slate-400">
          输入你对该标的的产业判断，系统把它与当前技术面结构并置，重点找出二者的背离——
          不预测涨跌，只发现值得研究的矛盾。
        </p>
      </div>

      {/* 快选维度：点一下即可，值直接对应 gap 的比对维度 */}
      <div className="flex flex-col gap-2">
        {DIMENSIONS.map((d) => (
          <div key={d.key} className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-400 w-20 shrink-0">{d.label}</span>
            {d.options.map((opt) => {
              const active = picks[d.key] === opt
              return (
                <button
                  key={opt}
                  type="button"
                  onClick={() => togglePick(d.key, opt)}
                  className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
                    active
                      ? 'bg-blue-600 border-blue-500 text-white'
                      : 'bg-slate-800 border-slate-700 text-slate-300 hover:border-slate-500'
                  }`}
                >
                  {opt}
                </button>
              )
            })}
          </div>
        ))}
      </div>

      {/* 可选补充：快选覆盖不到的细节 */}
      <textarea
        value={extra}
        onChange={(e) => setExtra(e.target.value)}
        rows={3}
        placeholder="可选补充：快选覆盖不到的细节，例如「大客户砍单」「新产能明年投产」「政策补贴退坡」……"
        className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 resize-y focus:outline-none focus:ring-2 focus:ring-blue-500"
      />

      <div className="flex items-center gap-3">
        <button
          onClick={handleRun}
          disabled={loading || !canRun}
          className="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-400 text-white text-sm font-semibold transition-colors"
        >
          {loading ? '分析中...' : '找出 GAP'}
        </button>
        <span className="text-xs text-slate-500">
          {canRun ? `基于 ${symbol.toUpperCase()} 当前技术面结构` : '至少选一个维度或填写补充'}
        </span>
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
