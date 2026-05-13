import apiClient from './client'

export interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
}

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export async function getMessages(): Promise<Message[]> {
  const res = await apiClient.get<{ messages: Message[] }>('/api/v1/messages')
  return res.data.messages
}

export async function clearMessages(): Promise<void> {
  await apiClient.delete('/api/v1/messages')
}

// 流式发送，回调每个 chunk
export async function sendMessageStream(
  messages: Message[],
  onChunk: (chunk: string) => void,
  onDone: () => void,
  onError: (err: string) => void,
): Promise<void> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null

  const response = await fetch(`${BASE_URL}/api/v1/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ messages }),
  })

  if (!response.ok) {
    onError(`请求失败 (${response.status})`)
    return
  }

  const reader = response.body?.getReader()
  const decoder = new TextDecoder()
  if (!reader) { onError('无法读取流'); return }

  let buffer = ''
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
        if (json.done) { onDone(); return }
        if (json.content) onChunk(json.content)
      } catch { /* ignore malformed */ }
    }
  }
  onDone()
}
