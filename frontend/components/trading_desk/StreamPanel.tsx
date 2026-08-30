'use client'

import { useEffect, useRef } from 'react'
import { useTradingDeskStore } from '@/lib/store/trading_desk'
import TurnCard from './TurnCard'

// 距底部 ≤ 阈值视为"贴底"：只有用户已贴底才跟随流式追加，否则保留
// 用户当前阅读点。用户主动上滑查看历史时不会被强制拉回底部。
const STICK_THRESHOLD = 40

export default function StreamPanel() {
  const turns = useTradingDeskStore((s) => s.turns)
  const runId = useTradingDeskStore((s) => s.runId)
  const status = useTradingDeskStore((s) => s.status)
  const scrollerRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  // 初始 true：第一次进入页面时滚到底，符合"实时推理"预期
  const stickyRef = useRef(true)

  // 监听用户滚动 → 更新贴底状态
  useEffect(() => {
    const el = scrollerRef.current
    if (!el) return
    const onScroll = () => {
      const distance = el.scrollHeight - el.scrollTop - el.clientHeight
      stickyRef.current = distance <= STICK_THRESHOLD
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  // 新一轮 run 开始 → 强制贴底：用户开新分析时希望看到最新输出
  useEffect(() => {
    stickyRef.current = true
  }, [runId])

  // 流式追加 → 仅在贴底时跟随
  const tail = turns.length > 0 ? turns[turns.length - 1].text.length : 0
  useEffect(() => {
    if (!stickyRef.current) return
    bottomRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  }, [turns.length, tail])

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
        <div
          ref={scrollerRef}
          className="stream-scrollable flex flex-1 flex-col gap-2.5 overflow-y-auto"
        >
          {turns.map((turn) => (
            <TurnCard key={turn.turnId} turn={turn} streaming={turn.turnId === streamingId} />
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  )
}