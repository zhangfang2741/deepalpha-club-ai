'use client'

import { useState, useEffect, useCallback } from 'react'
import { ChatThread } from '@/components/chat/ChatThread'
import {
  getChatHistory,
  clearChatHistory,
  getOrCreateSessionToken,
  clearStoredSessionToken,
} from '@/lib/api/chat'
import Spinner from '@/components/ui/Spinner'
import type { ThreadMessageLike } from '@assistant-ui/react'

interface ChatState {
  sessionToken: string
  initialMessages: readonly ThreadMessageLike[]
}

export default function ChatPage() {
  const [chatState, setChatState] = useState<ChatState | null>(null)
  const [chatKey, setChatKey] = useState(0)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function initChat() {
      try {
        const sessionToken = await getOrCreateSessionToken()
        let messages: ThreadMessageLike[] = []

        try {
          const history = await getChatHistory(sessionToken)
          messages = history.map((msg) => ({ role: msg.role, content: msg.content }))
        } catch {
          // 历史加载失败时以空会话启动
        }

        if (!cancelled) {
          setChatState({ sessionToken, initialMessages: messages })
        }
      } catch (err) {
        if (!cancelled) {
          setError('会话初始化失败，请刷新页面重试')
        }
      }
    }

    initChat()
    return () => { cancelled = true }
  }, [])

  const handleClearHistory = useCallback(async () => {
    if (!chatState) return
    try {
      await clearChatHistory(chatState.sessionToken)
    } catch {
      // 后端清除失败时仍重置前端
    }
    clearStoredSessionToken()

    // 创建新 session，重置对话
    try {
      const sessionToken = await getOrCreateSessionToken()
      setChatState({ sessionToken, initialMessages: [] })
      setChatKey((k) => k + 1)
    } catch {
      setError('创建新会话失败，请刷新页面重试')
    }
  }, [chatState])

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <h1 className="text-2xl font-bold text-gray-900 mb-4">AI 对话</h1>

      <div className="flex-1 min-h-0">
        {error ? (
          <div className="flex items-center justify-center h-full bg-gray-50 rounded-xl border border-gray-200">
            <p className="text-sm text-red-500">{error}</p>
          </div>
        ) : chatState === null ? (
          <div className="flex items-center justify-center h-full bg-gray-50 rounded-xl border border-gray-200">
            <Spinner className="w-6 h-6 text-gray-400" />
          </div>
        ) : (
          <ChatThread
            key={chatKey}
            sessionToken={chatState.sessionToken}
            initialMessages={chatState.initialMessages}
            onClearHistory={handleClearHistory}
          />
        )}
      </div>
    </div>
  )
}
