'use client'

import { Check, Loader2 } from 'lucide-react'
import { useTradingDeskStore } from '@/lib/store/trading_desk'
import SignalChip from './SignalChip'

export default function PipelinePanel() {
  const stages = useTradingDeskStore((s) => s.stages)
  const stageStatus = useTradingDeskStore((s) => s.stageStatus)
  const stageSignal = useTradingDeskStore((s) => s.stageSignal)

  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4">
      <div className="mb-3 font-mono text-[11px] font-bold uppercase tracking-wider text-gray-400">
        交易台成员
      </div>

      {stages.length === 0 ? (
        <p className="py-6 text-center text-xs text-gray-400">开始分析后显示阵容</p>
      ) : (
        // 窄屏横向滚动、桌面端纵向列表
        <div className="flex gap-2 overflow-x-auto sm:block sm:overflow-visible">
          {stages.map((stage) => {
            const status = stageStatus[stage.id] ?? 'pending'
            const signal = stageSignal[stage.id]
            return (
              <div
                key={stage.id}
                className={`flex w-44 flex-none gap-2.5 rounded-lg p-2 transition-colors sm:w-auto ${
                  status === 'active' ? 'bg-blue-50' : ''
                }`}
              >
                <div className="mt-0.5 flex-none">
                  {status === 'done' ? (
                    <span className="flex h-4 w-4 items-center justify-center rounded-full bg-green-600">
                      <Check className="h-2.5 w-2.5 text-white" strokeWidth={3} />
                    </span>
                  ) : status === 'active' ? (
                    <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
                  ) : (
                    <span className="block h-4 w-4 rounded-full border-2 border-gray-300" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div
                    className={`truncate text-[13px] font-semibold ${
                      status === 'pending' ? 'text-gray-400' : 'text-gray-900'
                    }`}
                  >
                    {stage.name}
                  </div>
                  <div className="truncate font-mono text-[10px] text-gray-400">{stage.role}</div>
                  {signal && (
                    <div className="mt-1.5">
                      <SignalChip dir={signal.dir} conf={signal.conf} />
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
