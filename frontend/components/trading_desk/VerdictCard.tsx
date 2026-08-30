'use client'

import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, ChevronRight } from 'lucide-react'
import { buildAuditChain, useTradingDeskStore } from '@/lib/store/trading_desk'

const ACTION: Record<string, { label: string; color: string }> = {
  BUY: { label: '买入', color: 'text-green-600' },
  SELL: { label: '卖出', color: 'text-red-500' },
  HOLD: { label: '观望', color: 'text-amber-600' },
}

/**
 * 置信度数字滚动到目标值。
 *
 * 初值直接在渲染时算（reduced-motion 或无动画需求时不进 effect），
 * 动画路径只通过 setInterval 的函数式更新推进——effect 体内不出现
 * 同步 setState（React 19 的 react-hooks/set-state-in-effect 规则）。
 */
function useCountUp(target: number | null): number {
  const prefersReduced = useMemo(
    () =>
      typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  )
  const [animated, setAnimated] = useState(0)

  useEffect(() => {
    if (target === null || prefersReduced) return

    const timer = window.setInterval(() => {
      setAnimated((current) => {
        const next = Math.min(current + 2, target)
        if (next >= target) window.clearInterval(timer)
        return next
      })
    }, 18)
    return () => window.clearInterval(timer)
  }, [target, prefersReduced])

  if (target === null) return 0
  if (prefersReduced) return target
  // 动画起点是 0；interval 里单调爬升到 target
  return animated
}

export default function VerdictCard() {
  const verdict = useTradingDeskStore((s) => s.verdict)
  const turns = useTradingDeskStore((s) => s.turns)
  const [auditOpen, setAuditOpen] = useState(false)

  const confPct = verdict ? Math.round(verdict.confidence * 100) : null
  const animatedConf = useCountUp(confPct)
  const action = verdict ? ACTION[verdict.signal] : null
  const audit = buildAuditChain(turns)

  return (
    <div
      className={`rounded-xl border p-4 ${
        verdict ? 'border-gray-200 bg-gray-50/70' : 'border-gray-100 bg-gray-50/40 opacity-60'
      }`}
    >
      <div className="flex items-baseline justify-between">
        <span className={`text-xl font-extrabold ${action?.color ?? 'text-gray-400'}`}>
          {action?.label ?? '—'}
        </span>
        <span className="font-mono text-[11px] text-gray-500">
          置信度 <b className="text-sm text-gray-900">{verdict ? `${animatedConf}%` : '—'}</b>
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2.5">
        <Field label="仓位" value={verdict ? `${(verdict.size_fraction * 100).toFixed(1)}%` : '—'} />
        <Field label="止损" value={verdict?.stop_loss != null ? String(verdict.stop_loss) : '—'} />
        <Field label="目标价" value={verdict?.target_price != null ? String(verdict.target_price) : '—'} />
        <Field
          label="周期"
          value={verdict?.time_horizon_days != null ? `${verdict.time_horizon_days} 天` : '—'}
        />
      </div>

      {/* 引擎在 JSON 解析失败走 fallback 时会置位 warning_message。
          必须显式展示——否则用户会把降级解析出的结论当作正常结论。 */}
      {verdict?.warning_message && (
        <div className="mt-3 flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-none text-amber-600" />
          <p className="text-[11.5px] leading-relaxed text-amber-800">
            结论解析降级：{verdict.warning_message}
          </p>
        </div>
      )}

      {verdict?.rationale && (
        <p className="mt-3 border-t border-gray-200 pt-3 text-[12px] leading-relaxed text-gray-600">
          {verdict.rationale}
        </p>
      )}

      {audit.length > 0 && (
        <div className="mt-3 border-t border-gray-200 pt-2">
          <button
            type="button"
            onClick={() => setAuditOpen((v) => !v)}
            className="flex items-center gap-1 font-mono text-[10px] text-blue-600 hover:text-blue-700"
          >
            <ChevronRight className={`h-3 w-3 transition-transform ${auditOpen ? 'rotate-90' : ''}`} />
            审计链（{audit.length} 步）
          </button>
          {auditOpen && (
            <ol className="mt-2 space-y-1.5 pl-4 text-[11px] leading-relaxed text-gray-500">
              {audit.map((entry, i) => (
                <li key={i} className="list-decimal">
                  <b className={entry.human ? 'text-blue-600' : 'text-gray-700'}>{entry.who}</b>
                  {' —— '}
                  {entry.excerpt}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] text-gray-400">{label}</div>
      <div className="mt-0.5 font-mono text-[13px] font-semibold text-gray-900">{value}</div>
    </div>
  )
}
