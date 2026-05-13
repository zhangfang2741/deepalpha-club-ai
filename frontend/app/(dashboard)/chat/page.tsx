'use client'

import { AssistantRuntimeProvider, useLocalRuntime, type ChatModelAdapter } from '@assistant-ui/react'
import { Thread, makeMarkdownText } from '@assistant-ui/react-ui'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

const MarkdownText = makeMarkdownText()

const chatAdapter: ChatModelAdapter = {
  async *run({ messages, abortSignal }) {
    const apiMessages = messages.map((msg) => ({
      role: msg.role as 'user' | 'assistant' | 'system',
      content: msg.content
        .filter((part): part is { type: 'text'; text: string } => part.type === 'text')
        .map((part) => part.text)
        .join(''),
    }))

    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null

    const response = await fetch(`${BASE_URL}/api/v1/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ messages: apiMessages }),
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

function ChatRuntime({ children }: { children: React.ReactNode }) {
  const runtime = useLocalRuntime(chatAdapter)
  return <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>
}

export default function ChatPage() {
  return (
    <div className="flex flex-col h-[calc(100vh-5rem)]">
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <h1 className="text-2xl font-bold text-gray-900">AI 对话</h1>
      </div>
      <div className="flex-1 min-h-0 rounded-xl border border-gray-200 overflow-hidden bg-white">
        <ChatRuntime>
          <Thread
            assistantMessage={{ components: { Text: MarkdownText } }}
            welcome={{ message: '开始与 AI 对话，分析市场动态' }}
          />
        </ChatRuntime>
      </div>
    </div>
  )
}
