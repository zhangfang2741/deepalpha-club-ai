import type { Turn } from '@/lib/store/trading_desk'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
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

const markdownComponents = {
  h1: ({ children }: { children?: React.ReactNode }) => (
    <h1 className="mt-3 mb-1 text-[15px] font-bold text-gray-900">{children}</h1>
  ),
  h2: ({ children }: { children?: React.ReactNode }) => (
    <h2 className="mt-3 mb-1 text-[14.5px] font-bold text-gray-900">{children}</h2>
  ),
  h3: ({ children }: { children?: React.ReactNode }) => (
    <h3 className="mt-2.5 mb-1 text-[14px] font-semibold text-gray-900">{children}</h3>
  ),
  h4: ({ children }: { children?: React.ReactNode }) => (
    <h4 className="mt-2 mb-0.5 text-[13.5px] font-semibold text-gray-800">{children}</h4>
  ),
  p: ({ children }: { children?: React.ReactNode }) => (
    <p className="my-1.5 text-[13.5px] leading-relaxed text-gray-700">{children}</p>
  ),
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul className="my-1.5 ml-5 list-disc text-[13.5px] leading-relaxed text-gray-700">{children}</ul>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol className="my-1.5 ml-5 list-decimal text-[13.5px] leading-relaxed text-gray-700">{children}</ol>
  ),
  li: ({ children }: { children?: React.ReactNode }) => (
    <li className="my-0.5">{children}</li>
  ),
  strong: ({ children }: { children?: React.ReactNode }) => (
    <strong className="font-semibold text-gray-900">{children}</strong>
  ),
  em: ({ children }: { children?: React.ReactNode }) => (
    <em className="italic">{children}</em>
  ),
  code: ({ children }: { children?: React.ReactNode }) => (
    <code className="rounded bg-gray-100 px-1 py-0.5 font-mono text-[12px] text-gray-800">{children}</code>
  ),
  pre: ({ children }: { children?: React.ReactNode }) => (
    <pre className="my-2 overflow-x-auto rounded-md bg-gray-900 px-3 py-2 font-mono text-[12px] leading-relaxed text-gray-100">
      {children}
    </pre>
  ),
  blockquote: ({ children }: { children?: React.ReactNode }) => (
    <blockquote className="my-2 border-l-2 border-gray-300 pl-3 text-[13px] italic text-gray-600">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-2 border-gray-200" />,
  a: ({ children, href }: { children?: React.ReactNode; href?: string }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-blue-600 underline hover:text-blue-800"
    >
      {children}
    </a>
  ),
  table: ({ children }: { children?: React.ReactNode }) => (
    <div className="my-2 overflow-x-auto">
      <table className="min-w-full border-collapse text-[12.5px]">{children}</table>
    </div>
  ),
  th: ({ children }: { children?: React.ReactNode }) => (
    <th className="border border-gray-200 bg-gray-50 px-2 py-1 text-left font-semibold text-gray-800">
      {children}
    </th>
  ),
  td: ({ children }: { children?: React.ReactNode }) => (
    <td className="border border-gray-200 px-2 py-1 text-gray-700">{children}</td>
  ),
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

      <div className="text-[13.5px] leading-relaxed text-gray-700">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {turn.text}
        </ReactMarkdown>
        {streaming && (
          // 打字光标：只在当前流式输出的卡片末尾显示
          <span className="ml-0.5 inline-block h-3.5 w-[3px] translate-y-[2px] bg-blue-600 motion-safe:animate-pulse" />
        )}
      </div>

      {turn.thinking && (
        <details className="mt-2 rounded-md border border-violet-200 bg-violet-50/60 px-3 py-2 text-[12px] leading-relaxed text-violet-900">
          <summary className="cursor-pointer font-mono text-[11px] font-semibold uppercase tracking-wider text-violet-700">
            推理过程
          </summary>
          <div className="mt-2">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {turn.thinking}
            </ReactMarkdown>
          </div>
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
