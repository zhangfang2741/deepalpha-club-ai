'use client'

import { useState, useEffect, useCallback } from 'react'
import { AssistantRuntimeProvider, MessagePrimitive } from '@assistant-ui/react'
import {
  useLangGraphRuntime,
  type LangChainMessage,
  type LangGraphMessagesEvent,
} from '@assistant-ui/react-langgraph'
import { Thread, makeMarkdownText } from '@assistant-ui/react-ui'
import remarkGfm from 'remark-gfm'
import {
  getLangGraphHistory,
  clearChatHistory,
  getOrCreateSessionToken,
  getValidSessionToken,
  createFreshSessionToken,
  clearStoredSessionToken,
} from '@/lib/api/chat'
import { useAuthStore } from '@/lib/store/auth'
import Spinner from '@/components/ui/Spinner'
import DashboardShell from '@/components/layout/DashboardShell'
import { ToolFallback, WriteTodosToolUI, TaskToolUI } from '@/components/chat/AgentToolUI'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
const THREAD_ID = 'main'

// 品牌头像：深靛渐变圆角 + 白色斜体 α（DeepAlpha / 金融「超额收益」）
const ASSISTANT_AVATAR_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6366f1"/><stop offset="1" stop-color="#312e81"/></linearGradient></defs><rect width="64" height="64" rx="16" fill="url(#g)"/><text x="32" y="34" text-anchor="middle" dominant-baseline="central" font-family="Georgia, 'Times New Roman', serif" font-size="34" font-style="italic" font-weight="600" fill="#ffffff">&#945;</text></svg>`
const ASSISTANT_AVATAR_SRC = `data:image/svg+xml,${encodeURIComponent(ASSISTANT_AVATAR_SVG)}`

const MarkdownText = makeMarkdownText({ remarkPlugins: [remarkGfm] })

/** 解析后端 SSE（每条 `data: {event,data}\n\n`）为 LangGraph 事件异步生成器。 */
async function* parseSSEStream(
  response: Response,
): AsyncGenerator<LangGraphMessagesEvent<LangChainMessage>> {
  const reader = response.body?.getReader()
  if (!reader) throw new Error('无法读取流')
  const decoder = new TextDecoder()
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
        const raw = line.slice(6).trim()
        if (!raw) continue
        try {
          yield JSON.parse(raw) as LangGraphMessagesEvent<LangChainMessage>
        } catch {
          /* 忽略半包/坏行 */
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

function UserMessageWithAvatar() {
  const user = useAuthStore((s) => s.user)
  const raw = user?.username ?? user?.email ?? 'U'
  const initials = raw.slice(0, 2).toUpperCase()

  return (
    <MessagePrimitive.Root className="flex justify-end items-end gap-2 w-full py-3 px-1">
      <div className="max-w-[75%] bg-gray-900 text-white rounded-2xl rounded-br-sm px-4 py-2.5 text-sm leading-relaxed">
        <MessagePrimitive.Content />
      </div>
      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-slate-600 to-slate-800 text-white text-xs font-semibold flex items-center justify-center flex-shrink-0 ring-1 ring-slate-900/10 shadow-sm">
        {initials}
      </div>
    </MessagePrimitive.Root>
  )
}

interface ChatRuntimeProps {
  children: React.ReactNode
}

function ChatRuntime({ children }: ChatRuntimeProps) {
  const stream = useCallback(
    async (
      messages: LangChainMessage[],
      { command, abortSignal }: { command?: { resume: string }; abortSignal: AbortSignal },
    ) => {
      const postStream = (token: string) =>
        fetch(`${BASE_URL}/api/v1/chatbot/langgraph/stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ messages, command }),
          signal: abortSignal,
        })

      // 用「有效」的 session token（过期会自动重建）；仍 401 时刷新并重试一次
      let response = await postStream(await getValidSessionToken())
      if (response.status === 401) {
        response = await postStream(await createFreshSessionToken())
      }
      if (!response.ok) throw new Error(`请求失败 (${response.status})`)
      return parseSSEStream(response)
    },
    [],
  )

  const load = useCallback(async () => {
    try {
      const messages = await getLangGraphHistory(await getValidSessionToken())
      return { messages: messages as unknown as LangChainMessage[] }
    } catch {
      return { messages: [] as LangChainMessage[] }
    }
  }, [])

  const create = useCallback(async () => ({ externalId: THREAD_ID }), [])

  const runtime = useLangGraphRuntime({
    threadId: THREAD_ID,
    stream,
    load,
    create,
    unstable_allowCancellation: true,
  })

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {/* 注册 Deep Agent 专用工具 UI */}
      <WriteTodosToolUI />
      <TaskToolUI />
      {children}
    </AssistantRuntimeProvider>
  )
}

export default function ChatPage() {
  const [sessionToken, setSessionToken] = useState<string | null>(null)
  const [chatKey, setChatKey] = useState(0)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getOrCreateSessionToken()
      .then((token) => {
        if (!cancelled) setSessionToken(token)
      })
      .catch(() => {
        if (!cancelled) setError('会话初始化失败，请刷新页面重试')
      })
    return () => {
      cancelled = true
    }
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
    <DashboardShell>
      <div className="-mx-6 -my-8 flex flex-col h-full overflow-hidden px-6 py-8">
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
            <ChatRuntime key={chatKey}>
              <Thread
                assistantAvatar={{ src: ASSISTANT_AVATAR_SRC, alt: 'DeepAlpha', fallback: 'α' }}
                assistantMessage={{ components: { Text: MarkdownText, ToolFallback } }}
                components={{ UserMessage: UserMessageWithAvatar }}
                strings={{ composer: { input: { placeholder: '输入你的问题，例如：深度分析一下 NVDA...' } } }}
                welcome={{
                  message:
                    '你好！我是 DeepAlpha Deep Agent 投研助手，面对复杂问题我会先规划再分步分析，可帮你研究美股、ETF 等市场动态。',
                  suggestions: [
                    { text: '📊 深度分析 NVDA', prompt: '深度分析一下 NVDA 最近的基本面、股价表现与主要风险' },
                    { text: '📈 缠论看 TSLA', prompt: '用缠论帮我分析 TSLA 近半年的买卖点与背驰情况' },
                    { text: '🔥 半导体板块情绪', prompt: '最近半导体板块的资金流向和市场情绪如何？' },
                    { text: '⚖️ AMD vs INTC', prompt: '对比一下 AMD 和 INTC 当前的投资价值' },
                  ],
                }}
              />
            </ChatRuntime>
          )}
        </div>
      </div>
    </DashboardShell>
  )
}
