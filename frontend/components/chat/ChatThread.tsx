'use client'

import { useMemo } from 'react'
import {
  AssistantRuntimeProvider,
  useLocalRuntime,
  ThreadPrimitive,
  MessagePrimitive,
  ComposerPrimitive,
  useMessagePartText,
  type ChatModelAdapter,
  type ThreadMessageLike,
  type TextMessagePartComponent,
} from '@assistant-ui/react'
import { Bot, SendHorizontal, Trash2 } from 'lucide-react'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

function buildChatAdapter(sessionToken: string): ChatModelAdapter {
  return {
    async *run({ messages, abortSignal }) {
      const lastMsg = messages[messages.length - 1]
      if (!lastMsg || lastMsg.role !== 'user') return

      const text = (lastMsg.content as Array<{ type: string; text?: string }>)
        .filter((c) => c.type === 'text' && c.text)
        .map((c) => c.text as string)
        .join('')

      if (!text.trim()) return

      const res = await fetch(`${API_URL}/api/v1/chatbot/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${sessionToken}`,
        },
        body: JSON.stringify({ messages: [{ role: 'user', content: text }] }),
        signal: abortSignal,
      })

      if (!res.ok) throw new Error(`请求失败：${res.status}`)

      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let accumulated = ''
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
            let data: { content: string; done: boolean }
            try {
              data = JSON.parse(line.slice(6))
            } catch {
              continue // skip malformed SSE chunks
            }
            if (data.done) {
              if (data.content) throw new Error(data.content) // backend error propagated via SSE
              break
            }
            if (data.content) {
              accumulated += data.content
              yield { content: [{ type: 'text' as const, text: accumulated }] }
            }
          }
        }
      } finally {
        reader.releaseLock()
      }
    },
  }
}

const MessageText: TextMessagePartComponent = () => {
  const { text } = useMessagePartText()
  return <span className="whitespace-pre-wrap break-words leading-relaxed">{text}</span>
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className="flex justify-end mb-3">
      <div className="max-w-[75%] bg-gray-900 text-white rounded-2xl rounded-br-sm px-4 py-2.5 text-sm">
        <MessagePrimitive.Content components={{ Text: MessageText }} />
      </div>
    </MessagePrimitive.Root>
  )
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="flex justify-start mb-3">
      <div className="flex items-start gap-2 max-w-[80%]">
        <div className="w-7 h-7 bg-blue-600 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
          <Bot className="w-4 h-4 text-white" />
        </div>
        <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-4 py-2.5 text-sm text-gray-800">
          <MessagePrimitive.Content components={{ Text: MessageText }} />
        </div>
      </div>
    </MessagePrimitive.Root>
  )
}

interface ChatThreadProps {
  sessionToken: string
  initialMessages?: readonly ThreadMessageLike[]
  onClearHistory?: () => void
}

export function ChatThread({ sessionToken, initialMessages, onClearHistory }: ChatThreadProps) {
  const chatAdapter = useMemo(() => buildChatAdapter(sessionToken), [sessionToken])
  const runtime = useLocalRuntime(chatAdapter, { initialMessages })

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadPrimitive.Root className="flex flex-col h-full">
        <ThreadPrimitive.Viewport className="relative flex-1 overflow-y-auto px-4 py-4 bg-gray-50 rounded-xl border border-gray-200 mb-3">
          <ThreadPrimitive.Empty>
            <div className="flex flex-col items-center justify-center h-full py-20 text-center">
              <div className="w-12 h-12 bg-blue-100 rounded-xl flex items-center justify-center mb-3">
                <Bot className="w-6 h-6 text-blue-600" />
              </div>
              <p className="text-sm text-gray-500">开始与 AI 对话，分析市场动态</p>
            </div>
          </ThreadPrimitive.Empty>

          <ThreadPrimitive.Messages
            components={{ UserMessage, AssistantMessage }}
          />

          <ThreadPrimitive.ScrollToBottom className="sticky bottom-2 ml-auto flex w-8 h-8 items-center justify-center rounded-full bg-white border border-gray-200 shadow-sm text-gray-500 hover:bg-gray-50 transition-colors" />
        </ThreadPrimitive.Viewport>

        <ComposerPrimitive.Root className="bg-white rounded-xl border border-gray-200 px-3 py-2.5 flex gap-2 items-end flex-shrink-0">
          <ComposerPrimitive.Input
            placeholder="输入你的问题..."
            className="flex-1 text-sm text-gray-700 outline-none bg-transparent placeholder:text-gray-400 resize-none py-0.5 max-h-32"
            submitMode="enter"
            minRows={1}
            maxRows={6}
          />
          {onClearHistory && (
            <button
              type="button"
              onClick={onClearHistory}
              title="清空对话"
              className="p-1.5 text-gray-400 hover:text-gray-600 transition-colors flex-shrink-0"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
          <ComposerPrimitive.Send className="px-3 py-2 bg-gray-900 text-white text-sm font-medium rounded-lg disabled:opacity-40 transition-colors hover:bg-gray-700 flex items-center gap-1.5 flex-shrink-0">
            <SendHorizontal className="w-4 h-4" />
            发送
          </ComposerPrimitive.Send>
        </ComposerPrimitive.Root>
      </ThreadPrimitive.Root>
    </AssistantRuntimeProvider>
  )
}
