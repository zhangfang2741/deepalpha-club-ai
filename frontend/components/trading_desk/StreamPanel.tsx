'use client'

import { useEffect, useRef } from 'react'
import { useTradingDeskStore } from '@/lib/store/trading_desk'
import TurnCard from './TurnCard'

export default function StreamPanel() {
  const turns = useTradingDeskStore((s) => s.turns)
  const status = useTradingDeskStore((s) => s.status)
  const bottomRef = useRef<HTMLDivElement>(null)

  // 跟随最新内容滚动。依赖 turns 长度与最后一张卡片的文本长度，
  // 这样流式追加 token 时也会持续跟随。
  const tail = turns.length > 0 ? turns[turns.length - 1].text.length : 0
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [turns.length, tail])

  // 正在流式输出的卡片：第一张尚未 turn.done 的
  const streamingId =
    status === 'running' ? (turns.find((t) => !t.done)?.turnId ?? null) : null

  return (
    <div className="flex min-h-[28rem] flex-col rounded-2xl border border-gray-200 bg-white p-4">
      <div className="mb-3 font-mono text-[11px] font-bold uppercase tracking-wider text-gray-400">
        实时推理
      </div>

      {turns.length === 0 ? (
        <div className="flex flex-1 items-center justify-center px-6 py-16 text-center">
          <div>
            <p className="text-sm font-semibold text-gray-500">交易台还很安静。</p>
            <p className="mt-2 text-[13px] leading-relaxed text-gray-400">
              输入标的、点「开始分析」。
              <br />
              看每个 agent 实时推理、辩论、给出结论。
            </p>
          </div>
        </div>
      ) : (
        <div className="flex flex-1 flex-col gap-2.5 overflow-y-auto">
          {turns.map((turn) => (
            <TurnCard key={turn.turnId} turn={turn} streaming={turn.turnId === streamingId} />
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  )
}
