'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Send, Trash2, Bot, User, ChevronDown } from 'lucide-react'
import { getMessages, clearMessages, sendMessageStream } from '@/lib/api/chat'
import type { Message } from '@/lib/api/chat'

// 渲染单条消息内容（AI 用 Markdown，用户用纯文本）
function MessageContent({ role, content }: { role: string; content: string }) {
  if (role === 'user') {
    return <p className="text-sm leading-relaxed whitespace-pre-wrap">{content}</p>
  }
  return (
    <div className="prose prose-sm max-w-none text-slate-800
      prose-headings:font-semibold prose-headings:text-slate-900 prose-headings:mt-3 prose-headings:mb-1
      prose-p:my-1 prose-p:leading-relaxed
      prose-ul:my-1 prose-ul:pl-4 prose-li:my-0.5
      prose-ol:my-1 prose-ol:pl-4
      prose-strong:text-slate-900 prose-strong:font-semibold
      prose-code:bg-slate-100 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:text-slate-700
      prose-pre:bg-slate-100 prose-pre:rounded-lg prose-pre:p-3
      prose-blockquote:border-l-blue-400 prose-blockquote:text-slate-600
      prose-hr:border-slate-200
      prose-table:text-xs prose-th:bg-slate-50 prose-th:px-3 prose-th:py-2 prose-td:px-3 prose-td:py-1.5">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  )
}

function MessageBubble({ msg, isStreaming }: { msg: Message; isStreaming?: boolean }) {
  const isUser = msg.role === 'user'

  if (isUser) {
    return (
      <div className="flex items-end justify-end gap-2">
        <div className="max-w-[72%] bg-slate-900 text-white rounded-2xl rounded-br-sm px-4 py-2.5">
          <MessageContent role="user" content={msg.content} />
        </div>
        <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center flex-shrink-0">
          <User className="w-4 h-4 text-white" />
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-end gap-2">
      <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center flex-shrink-0">
        <Bot className="w-4 h-4 text-white" />
      </div>
      <div className="max-w-[80%] bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-4 py-2.5 shadow-sm">
        <MessageContent role="assistant" content={msg.content} />
        {isStreaming && (
          <span className="inline-block w-1.5 h-4 bg-blue-500 rounded-sm animate-pulse ml-0.5 align-middle" />
        )}
      </div>
    </div>
  )
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [initializing, setInitializing] = useState(true)
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // 加载历史消息
  useEffect(() => {
    getMessages()
      .then((msgs) => setMessages(msgs.filter((m) => m.role !== 'system')))
      .catch(() => {})
      .finally(() => setInitializing(false))
  }, [])

  const scrollToBottom = useCallback((smooth = true) => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: smooth ? 'smooth' : 'instant',
    })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  // 显示/隐藏滚动到底部按钮
  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    setShowScrollBtn(distFromBottom > 120)
  }

  const handleSend = async () => {
    const text = input.trim()
    if (!text || loading) return
    setInput('')

    const userMsg: Message = { role: 'user', content: text }
    const newMessages = [...messages, userMsg]
    setMessages(newMessages)
    setLoading(true)

    // 占位 AI 消息
    const aiPlaceholder: Message = { role: 'assistant', content: '' }
    setMessages([...newMessages, aiPlaceholder])

    await sendMessageStream(
      newMessages,
      (chunk) => {
        setMessages((prev) => {
          const updated = [...prev]
          updated[updated.length - 1] = {
            role: 'assistant',
            content: updated[updated.length - 1].content + chunk,
          }
          return updated
        })
      },
      () => setLoading(false),
      (err) => {
        setMessages((prev) => {
          const updated = [...prev]
          updated[updated.length - 1] = { role: 'assistant', content: `错误：${err}` }
          return updated
        })
        setLoading(false)
      },
    )

    inputRef.current?.focus()
  }

  const handleClear = async () => {
    await clearMessages().catch(() => {})
    setMessages([])
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const visibleMessages = messages.filter((m) => m.role !== 'system')

  return (
    <div className="flex flex-col h-[calc(100vh-5rem)]">
      {/* 页头 */}
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <h1 className="text-2xl font-bold text-gray-900">AI 对话</h1>
        {visibleMessages.length > 0 && (
          <button
            onClick={handleClear}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-500 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors border border-gray-200"
          >
            <Trash2 className="w-3.5 h-3.5" />
            清空对话
          </button>
        )}
      </div>

      {/* 消息区 */}
      <div className="relative flex-1 min-h-0">
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="h-full overflow-y-auto bg-white rounded-xl border border-gray-200 p-4 flex flex-col gap-4"
        >
          {initializing && (
            <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">加载中...</div>
          )}

          {!initializing && visibleMessages.length === 0 && (
            <div className="flex-1 flex flex-col items-center justify-center text-center gap-3">
              <div className="w-14 h-14 bg-blue-50 rounded-2xl flex items-center justify-center">
                <Bot className="w-7 h-7 text-blue-500" />
              </div>
              <p className="text-sm text-gray-500">开始与 AI 对话，分析市场动态</p>
            </div>
          )}

          {visibleMessages.map((msg, i) => (
            <MessageBubble
              key={i}
              msg={msg}
              isStreaming={loading && i === visibleMessages.length - 1 && msg.role === 'assistant'}
            />
          ))}
        </div>

        {/* 滚动到底部按钮 */}
        {showScrollBtn && (
          <button
            onClick={() => scrollToBottom()}
            className="absolute bottom-3 right-3 w-8 h-8 bg-white border border-gray-200 rounded-full shadow-md flex items-center justify-center hover:bg-gray-50 transition-colors z-10"
          >
            <ChevronDown className="w-4 h-4 text-gray-500" />
          </button>
        )}
      </div>

      {/* 输入区 */}
      <div className="mt-3 bg-white rounded-xl border border-gray-200 p-3 flex gap-3 items-end flex-shrink-0 shadow-sm">
        <textarea
          ref={inputRef}
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入你的问题... (Enter 发送，Shift+Enter 换行)"
          disabled={loading}
          className="flex-1 text-sm text-gray-700 outline-none bg-transparent placeholder:text-gray-400 disabled:cursor-not-allowed resize-none max-h-32 leading-relaxed"
          style={{ height: 'auto' }}
          onInput={(e) => {
            const t = e.currentTarget
            t.style.height = 'auto'
            t.style.height = `${t.scrollHeight}px`
          }}
        />
        <button
          onClick={handleSend}
          disabled={loading || !input.trim()}
          className="flex items-center gap-1.5 px-4 py-2 bg-slate-900 hover:bg-slate-700 text-white text-sm font-medium rounded-lg disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex-shrink-0"
        >
          <Send className="w-3.5 h-3.5" />
          发送
        </button>
      </div>
    </div>
  )
}
