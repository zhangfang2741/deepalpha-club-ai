import apiClient from './client'
import { createChatSession } from './auth'

export interface BackendChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

const SESSION_TOKEN_KEY = 'chat_session_token'

export function getStoredSessionToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(SESSION_TOKEN_KEY)
}

function storeSessionToken(token: string): void {
  localStorage.setItem(SESSION_TOKEN_KEY, token)
}

export function clearStoredSessionToken(): void {
  localStorage.removeItem(SESSION_TOKEN_KEY)
}

export async function getOrCreateSessionToken(): Promise<string> {
  const stored = getStoredSessionToken()
  if (stored) return stored

  const session = await createChatSession()
  const token = session.token.access_token
  storeSessionToken(token)
  return token
}

export async function getChatHistory(sessionToken: string): Promise<BackendChatMessage[]> {
  const { data } = await apiClient.get<{ messages: BackendChatMessage[] }>(
    '/api/v1/chatbot/messages',
    { headers: { Authorization: `Bearer ${sessionToken}` } }
  )
  return data.messages ?? []
}

export async function clearChatHistory(sessionToken: string): Promise<void> {
  await apiClient.delete('/api/v1/chatbot/messages', {
    headers: { Authorization: `Bearer ${sessionToken}` },
  })
}
