'use client'

import { useTradingDeskStore } from '@/lib/store/trading_desk'

export default function ConsensusMeter() {
  const consensus = useTradingDeskStore((s) => s.consensus)
  const total = consensus ? consensus.bull + consensus.neutral + consensus.bear : 0
  const pct = (n: number) => (total > 0 ? (n / total) * 100 : 0)

  return (
    <div>
      <div className="mb-1.5 flex justify-between font-mono text-[10px] text-gray-400">
        <span>共识</span>
        <span>
          {consensus
            ? `多${consensus.bull} 中${consensus.neutral} 空${consensus.bear} · ${consensus.lean}`
            : '—'}
        </span>
      </div>
      <div className="flex h-2 overflow-hidden rounded-full bg-gray-100">
        <span
          className="h-full bg-green-600 transition-[width] duration-500"
          style={{ width: `${pct(consensus?.bull ?? 0)}%` }}
        />
        <span
          className="h-full bg-amber-500 transition-[width] duration-500"
          style={{ width: `${pct(consensus?.neutral ?? 0)}%` }}
        />
        <span
          className="h-full bg-red-500 transition-[width] duration-500"
          style={{ width: `${pct(consensus?.bear ?? 0)}%` }}
        />
      </div>
    </div>
  )
}
