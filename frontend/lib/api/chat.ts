import apiClient, { BASE_URL } from './client'
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

/** 解析 JWT 的 exp，判断 token 是否已过期（或将在 60s 内过期）。无法解析视为过期。 */
function isTokenExpired(token: string): boolean {
  try {
    const payload = token.split('.')[1]
    if (!payload) return true
    const json = JSON.parse(
      atob(payload.replace(/-/g, '+').replace(/_/g, '/')),
    ) as { exp?: number }
    if (!json.exp) return false
    return Date.now() / 1000 >= json.exp - 60
  } catch {
    return true
  }
}

/** 强制新建一个 chat session 并存储其 token（登录鉴权由 apiClient 拦截器带上）。 */
export async function createFreshSessionToken(): Promise<string> {
  clearStoredSessionToken()
  const session = await createChatSession()
  const token = session.token.access_token
  storeSessionToken(token)
  return token
}

/** 返回一个「有效」的 chat session token：本地已过期/缺失时自动重建。 */
export async function getValidSessionToken(): Promise<string> {
  const stored = getStoredSessionToken()
  if (stored && !isTokenExpired(stored)) return stored
  return createFreshSessionToken()
}

/** 兼容旧调用：等价于获取一个有效的 session token。 */
export async function getOrCreateSessionToken(): Promise<string> {
  return getValidSessionToken()
}

export async function getChatHistory(sessionToken: string): Promise<BackendChatMessage[]> {
  const { data } = await apiClient.get<{ messages: BackendChatMessage[] }>(
    '/api/v1/chatbot/messages',
    { headers: { Authorization: `Bearer ${sessionToken}` } }
  )
  return data.messages ?? []
}

export async function clearChatHistory(sessionToken: string): Promise<void> {
  // 原生 fetch：避免 apiClient 拦截器把 Authorization 覆盖成登录 token。
  await fetch(`${BASE_URL}/api/v1/chatbot/messages`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${sessionToken}` },
  })
}

// LangChain 风格的历史消息（含工具调用），供 useLangGraphRuntime 的 load 恢复。
// 结构与 @assistant-ui/react-langgraph 的 LangChainMessage 对齐（type: human/ai/tool）。
export interface LangChainHistoryMessage {
  id?: string
  type: 'human' | 'ai' | 'tool' | 'system'
  content: unknown
  [key: string]: unknown
}

// 用原生 fetch（而非 apiClient）：apiClient 的请求拦截器会把 Authorization 覆盖成登录
// access_token，而这里需要用 chat session token 鉴权。401 时刷新 session 并重试一次。
export async function getLangGraphHistory(
  sessionToken: string,
): Promise<LangChainHistoryMessage[]> {
  const fetchHistory = async (token: string): Promise<Response> =>
    fetch(`${BASE_URL}/api/v1/chatbot/langgraph/history`, {
      headers: { Authorization: `Bearer ${token}` },
    })

  let res = await fetchHistory(sessionToken)
  if (res.status === 401) {
    res = await fetchHistory(await createFreshSessionToken())
  }
  if (!res.ok) return []
  const data = (await res.json()) as { messages?: LangChainHistoryMessage[] }
  return data.messages ?? []
}
