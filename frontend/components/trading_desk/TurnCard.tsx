import type { Turn } from '@/lib/store/trading_desk'
import SignalChip from './SignalChip'

/**
 * 辩论卡片按 polarity 分色分栏：前端不必认识具体门派，因此同一套
 * 渲染既能画多空二元辩论，也能画激进/中立/保守三方辩论。
 */
function toneOf(turn: Turn): { card: string; avatar: string; name: string; indent: string } {
  if (turn.human) {
    return {
      card: 'border-blue-500 bg-blue-50/70',
      avatar: 'bg-blue-100 text-blue-700 border-blue-300',
      name: 'text-blue-700',
      indent: '',
    }
  }
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
        avatar: 'bg-red-100 text-red-700 border-red-300',
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

export default function TurnCard({ turn, streaming }: { turn: Turn; streaming: boolean }) {
  const tone = toneOf(turn)

  return (
    <div className={`rounded-xl border p-3.5 ${tone.card} ${tone.indent}`}>
      <div className="mb-2 flex items-center gap-2">
        <span
          className={`flex h-6 w-6 flex-none items-center justify-center rounded-md border font-mono text-[10px] font-bold ${tone.avatar}`}
        >
          {turn.avatar}
        </span>
        <span className={`text-[13px] font-semibold ${tone.name}`}>{turn.name}</span>
        {turn.role && <span className="ml-auto font-mono text-[10px] text-gray-400">{turn.role}</span>}
      </div>

      {turn.tools.length > 0 && (
        <div className="mb-1.5 flex flex-wrap gap-1.5">
          {turn.tools.map((tool, i) => (
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
        {turn.text}
        {streaming && (
          // 打字光标：只在当前流式输出的卡片末尾显示
          <span className="ml-0.5 inline-block h-3.5 w-[3px] translate-y-[2px] bg-blue-600 motion-safe:animate-pulse" />
        )}
      </p>

      {turn.thinking && (
        <details className="mt-2 rounded-md border border-violet-200 bg-violet-50/60 px-3 py-2 text-[12px] leading-relaxed text-violet-900">
          <summary className="cursor-pointer font-mono text-[11px] font-semibold uppercase tracking-wider text-violet-700">
            推理过程
          </summary>
          <p className="mt-2 whitespace-pre-wrap">{turn.thinking}</p>
        </details>
      )}

      {turn.signal && (
        <div className="mt-2">
          <SignalChip dir={turn.signal.dir} conf={turn.signal.conf} extracted={turn.signal.extracted} />
        </div>
      )}
    </div>
  )
}
