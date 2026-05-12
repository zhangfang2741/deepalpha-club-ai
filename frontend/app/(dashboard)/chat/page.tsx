'use client'

import { useState, useEffect, useCallback } from 'react'
import { ChatThread } from '@/components/chat/ChatThread'
import { getChatHistory, clearChatHistory } from '@/lib/api/chat'
import Spinner from '@/components/ui/Spinner'
import type { ThreadMessageLike } from '@assistant-ui/react'

export default function ChatPage() {
  const [initialMessages, setInitialMessages] = useState<readonly ThreadMessageLike[] | null>(null)
  const [chatKey, setChatKey] = useState(0)

  useEffect(() => {
    getChatHistory()
      .then((history) =>
        setInitialMessages(history.map((msg) => ({ role: msg.role, content: msg.content })))
      )
      .catch(() => setInitialMessages([]))
  }, [])

  const handleClearHistory = useCallback(async () => {
    try {
      await clearChatHistory()
    } catch {
      // proceed with local reset even if backend fails
    }
    setInitialMessages([])
    setChatKey((k) => k + 1)
  }, [])

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <h1 className="text-2xl font-bold text-gray-900 mb-4">AI 对话</h1>

      <div className="flex-1 min-h-0">
        {initialMessages === null ? (
          <div className="flex items-center justify-center h-full bg-gray-50 rounded-xl border border-gray-200">
            <Spinner className="w-6 h-6 text-gray-400" />
          </div>
        ) : (
          <ChatThread
            key={chatKey}
            initialMessages={initialMessages}
            onClearHistory={handleClearHistory}
          />
        )}
      </div>
    </div>
  )
}
