'use client'

import { useMemo, useState, useEffect, useCallback } from 'react'
import {
  AssistantRuntimeProvider,
  useLocalRuntime,
  ExportedMessageRepository,
  type ChatModelAdapter,
  type ThreadHistoryAdapter,
  type ExportedMessageRepositoryItem,
} from '@assistant-ui/react'
import { Thread, makeMarkdownText } from '@assistant-ui/react-ui'
import {
  getChatHistory,
  clearChatHistory,
  getOrCreateSessionToken,
  clearStoredSessionToken,
} from '@/lib/api/chat'
import Spinner from '@/components/ui/Spinner'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

const MarkdownText = makeMarkdownText()

function buildChatAdapter(sessionToken: string): ChatModelAdapter {
  return {
    async *run({ messages, abortSignal }) {
      const lastMsg = messages[messages.length - 1]
      if (!lastMsg || lastMsg.role !== 'user') return

      const text = lastMsg.content
        .filter((part): part is { type: 'text'; text: string } => part.type === 'text')
        .map((part) => part.text)
        .join('')

      if (!text.trim()) return

      const response = await fetch(`${BASE_URL}/api/v1/chatbot/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${sessionToken}`,
        },
        body: JSON.stringify({ messages: [{ role: 'user', content: text }] }),
        signal: abortSignal,
      })

      if (!response.ok) throw new Error(`请求失败 (${response.status})`)

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      if (!reader) throw new Error('无法读取流')

      let fullText = ''
      let buffer = ''

      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            try {
              const json = JSON.parse(line.slice(6))
              if (json.done) return
              if (json.content) {
                fullText += json.content
                yield { content: [{ type: 'text' as const, text: fullText }] }
              }
            } catch { /* ignore malformed */ }
          }
        }
      } finally {
        reader.releaseLock()
      }
    },
  }
}

function buildHistoryAdapter(sessionToken: string): ThreadHistoryAdapter {
  return {
    async load() {
      try {
        const messages = await getChatHistory(sessionToken)
        return ExportedMessageRepository.fromArray(
          messages.map((msg) => ({ role: msg.role, content: msg.content }))
        )
      } catch {
        return { messages: [] }
      }
    },
    // Backend persists messages during streaming; no separate save needed
    async append(_item: ExportedMessageRepositoryItem) {},
  }
}

interface ChatRuntimeProps {
  sessionToken: string
  children: React.ReactNode
}

function ChatRuntime({ sessionToken, children }: ChatRuntimeProps) {
  const chatAdapter = useMemo(() => buildChatAdapter(sessionToken), [sessionToken])
  const historyAdapter = useMemo(() => buildHistoryAdapter(sessionToken), [sessionToken])
  const runtime = useLocalRuntime(chatAdapter, { adapters: { history: historyAdapter } })
  return <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>
}

export default function ChatPage() {
  const [sessionToken, setSessionToken] = useState<string | null>(null)
  const [chatKey, setChatKey] = useState(0)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getOrCreateSessionToken()
      .then((token) => { if (!cancelled) setSessionToken(token) })
      .catch(() => { if (!cancelled) setError('会话初始化失败，请刷新页面重试') })
    return () => { cancelled = true }
  }, [])

  const handleClearHistory = useCallback(async () => {
    if (!sessionToken) return
    try {
      await clearChatHistory(sessionToken)
    } catch {
      // 后端清除失败时仍重置前端
    }
    clearStoredSessionToken()
    try {
      const newToken = await getOrCreateSessionToken()
      setSessionToken(newToken)
      setChatKey((k) => k + 1)
    } catch {
      setError('创建新会话失败，请刷新页面重试')
    }
  }, [sessionToken])

  return (
    <div className="flex flex-col h-[calc(100vh-5rem)]">
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <h1 className="text-2xl font-bold text-gray-900">AI 对话</h1>
        {sessionToken && (
          <button
            type="button"
            onClick={handleClearHistory}
            className="text-sm text-gray-400 hover:text-gray-600 px-3 py-1 rounded-lg hover:bg-gray-100 transition-colors"
          >
            清空对话
          </button>
        )}
      </div>
      <div className="flex-1 min-h-0 rounded-xl border border-gray-200 overflow-hidden bg-white">
        {error ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-sm text-red-500">{error}</p>
          </div>
        ) : sessionToken === null ? (
          <div className="flex items-center justify-center h-full">
            <Spinner className="w-6 h-6 text-gray-400" />
          </div>
        ) : (
          <ChatRuntime key={chatKey} sessionToken={sessionToken}>
            <Thread
              assistantMessage={{ components: { Text: MarkdownText } }}
              welcome={{ message: '开始与 AI 对话，分析市场动态' }}
            />
          </ChatRuntime>
        )}
      </div>
    </div>
  )
}
