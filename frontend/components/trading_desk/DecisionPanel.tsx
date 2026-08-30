'use client'

import { useTradingDeskStore } from '@/lib/store/trading_desk'
import ConsensusMeter from './ConsensusMeter'
import SignalChip from './SignalChip'
import VerdictCard from './VerdictCard'

export default function DecisionPanel() {
  const signals = useTradingDeskStore((s) => s.signals)

  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4">
      <div className="mb-3 font-mono text-[11px] font-bold uppercase tracking-wider text-gray-400">
        决策
      </div>

      <div className="flex flex-col gap-4">
        <ConsensusMeter />

        {signals.length > 0 && (
          <div className="flex flex-col gap-2">
            {signals.map((s, i) => (
              <div key={`${s.name}-${i}`} className="flex items-center justify-between gap-2">
                <span className="truncate text-[12px] text-gray-500">{s.name}</span>
                <SignalChip dir={s.dir} conf={s.conf} extracted={s.extracted} />
              </div>
            ))}
          </div>
        )}

        <VerdictCard />
      </div>
    </div>
  )
}
