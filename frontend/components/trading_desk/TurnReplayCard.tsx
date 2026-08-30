import type { TurnRecord } from '@/lib/api/trading_desk'
import SignalChip from './SignalChip'

/**
 * 回放页用的卡片：与实时页 TurnCard 共用同一套极性分色逻辑，但不依赖 store。
 *
 * - 不显示流式光标（streaming=false）
 * - 不消费 agent.signal 事件（信号已经从 signals 列表扁平化了）
 * - 仍按 debate polarity 分栏配色，让多空二元 / 三方风险辩论一目了然
 */
function toneOf(turn: TurnRecord): { card: string; avatar: string; name: string; indent: string } {
  switch (turn.debate?.polarity) {
    case 'bull':
      return {
        card: 'border-green-200 bg-gradient-to-b from-green-50/70 to-white',
        avatar: 'bg-green-100 text-green-700 border-green-300',
        name: 'text-green-700',
        indent: '',
      }
    case 'bear':
      return {
        card: 'border-red-200 bg-gradient-to-b from-red-50/70 to-white',
        avatar: 'bg-red-100 text-red-600 border-red-300',
        name: 'text-red-600',
        indent: 'ml-0 sm:ml-8',
      }
    case 'neutral':
      return {
        card: 'border-amber-200 bg-gradient-to-b from-amber-50/70 to-white',
        avatar: 'bg-amber-100 text-amber-700 border-amber-300',
        name: 'text-amber-700',
        indent: 'ml-0 sm:ml-4',
      }
    default:
      return {
        card: 'border-gray-200 bg-gray-50/60',
        avatar: 'bg-gray-100 text-gray-500 border-gray-200',
        name: 'text-gray-900',
        indent: '',
      }
  }
}

export default function TurnReplayCard({
  turn,
  signal,
}: {
  turn: TurnRecord
  signal?: { dir: 'bull' | 'bear' | 'neutral'; conf: number; extracted: boolean } | null
}) {
  const tone = toneOf(turn)
  const debateLabel = turn.debate
    ? `${turn.debate.side_label} · 第 ${turn.debate.round} 轮`
    : null

  return (
    <div className={`rounded-xl border p-3.5 ${tone.card} ${tone.indent}`}>
      <div className="mb-2 flex items-center gap-2">
        <span
          className={`flex h-6 w-6 flex-none items-center justify-center rounded-md border font-mono text-[10px] font-bold ${tone.avatar}`}
        >
          {turn.avatar || turn.name.slice(0, 2)}
        </span>
        <span className={`text-[13px] font-semibold ${tone.name}`}>{turn.name}</span>
        {debateLabel && (
          <span className="rounded bg-white/70 px-1.5 py-0.5 font-mono text-[10px] text-gray-500">
            {debateLabel}
          </span>
        )}
        {turn.role && (
          <span className="ml-auto font-mono text-[10px] text-gray-400">{turn.role}</span>
        )}
      </div>

      {turn.tool_calls.length > 0 && (
        <div className="mb-1.5 flex flex-wrap gap-1.5">
          {turn.tool_calls.map((tool, i) => (
            <span
              key={`${tool}-${i}`}
              className="rounded bg-blue-50 px-1.5 py-0.5 font-mono text-[10px] text-blue-600"
            >
              ⚙ {tool}
            </span>
          ))}
        </div>
      )}

      <p className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-gray-700">
        {turn.text || <span className="italic text-gray-400">（无内容）</span>}
      </p>

      {signal && (
        <div className="mt-2">
          <SignalChip dir={signal.dir} conf={signal.conf} extracted={signal.extracted} />
        </div>
      )}
    </div>
  )
}