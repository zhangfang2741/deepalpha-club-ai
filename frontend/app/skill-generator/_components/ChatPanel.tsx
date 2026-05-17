'use client'
import { useEffect, useRef, useState } from 'react'

export type ChatMessage = {
  role: 'user' | 'assistant'
  text: string  // 只放给用户看的纯文字（代码块已剥除）
}

interface Props {
  messages: ChatMessage[]
  streamingText: string  // 当前正在流式接收的 AI 回复（已剥代码）
  generating: boolean
  onSubmit: (text: string) => void
  placeholder?: string
}

export function ChatPanel({ messages, streamingText, generating, onSubmit, placeholder }: Props) {
  const [draft, setDraft] = useState('')
  const listRef = useRef<HTMLDivElement>(null)

  // 自动滚到底
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages.length, streamingText])

  const send = () => {
    const t = draft.trim()
    if (!t || generating) return
    onSubmit(t)
    setDraft('')
  }

  return (
    <div className="h-full flex flex-col bg-white">
      <div ref={listRef} className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && !streamingText && (
          <div className="text-center text-sm text-gray-400 mt-8">
            告诉 AI 你想要什么因子<br />
            <span className="text-xs">例如「MACD 金叉信号」「20 日动量」</span>
          </div>
        )}
        {messages.map((m, i) => (
          <Bubble key={i} role={m.role} text={m.text} />
        ))}
        {streamingText && <Bubble role="assistant" text={streamingText} streaming />}
        {generating && !streamingText && (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <div className="w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            AI 思考中…
          </div>
        )}
      </div>
      <div className="border-t border-gray-200 p-3">
        <div className="flex gap-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                send()
              }
            }}
            placeholder={placeholder || '描述你想要的因子（Enter 发送，Shift+Enter 换行）'}
            rows={2}
            disabled={generating}
            className="flex-1 resize-none border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50"
          />
          <button
            onClick={send}
            disabled={generating || !draft.trim()}
            className="px-4 rounded-lg text-white text-sm font-medium bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            发送
          </button>
        </div>
      </div>
    </div>
  )
}

function Bubble({ role, text, streaming }: { role: 'user' | 'assistant'; text: string; streaming?: boolean }) {
  const isUser = role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] px-3 py-2 rounded-2xl text-sm whitespace-pre-wrap leading-relaxed ${
          isUser
            ? 'bg-blue-600 text-white rounded-br-sm'
            : 'bg-gray-100 text-gray-800 rounded-bl-sm'
        }`}
      >
        {text}
        {streaming && <span className="ml-1 inline-block w-1.5 h-3.5 bg-gray-400 animate-pulse align-middle" />}
      </div>
    </div>
  )
}
