/**
 * 因子探索 API：Skill 代码生成（SSE）+ K 线预加载 + Skill 执行
 * 使用 native fetch 处理 SSE 流式响应，Axios 不支持 ReadableStream
 */

import client from './client'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export type Freq = 'daily' | 'weekly'

export interface SkillMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface KlineBar {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface KlineResponse {
  symbol: string
  freq: string
  klines: KlineBar[]
}

export interface FactorPoint {
  time: string
  value: number
}

export interface SkillRunResponse {
  symbol: string
  output_type: string
  factor: FactorPoint[]
}

function getToken(): string {
  if (typeof window === 'undefined') return ''
  return localStorage.getItem('access_token') ?? ''
}

/** 流式生成 Skill 代码（SSE），逐 chunk 回调 */
export async function generateSkillStream(
  messages: SkillMessage[],
  onChunk: (text: string) => void,
  onDone: () => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = getToken()
  if (!token) throw new Error('未登录，请先登录')

  const response = await fetch(`${BASE_URL}/api/v1/skills/generate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ messages }),
    signal,
  })

  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText)
    throw new Error(`生成请求失败 (${response.status}): ${text}`)
  }

  const reader = response.body?.getReader()
  if (!reader) throw new Error('无法读取响应流')
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
        try {
          const data = JSON.parse(line.slice(6))
          if (data.done) {
            onDone()
            return
          }
          if (data.content) onChunk(data.content)
        } catch {
          // 忽略格式异常行
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
  onDone()
}

/** 预加载 K 线数据（同时写入后端 Redis 缓存） */
export async function fetchKline(
  symbol: string,
  startDate: string,
  endDate: string,
  freq: Freq,
): Promise<KlineResponse> {
  const token = getToken()
  const params = new URLSearchParams({ symbol, start_date: startDate, end_date: endDate, freq })
  const response = await fetch(`${BASE_URL}/api/v1/skills/kline?${params}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText)
    throw new Error(`K 线数据加载失败 (${response.status}): ${text}`)
  }
  return response.json()
}

/** 执行 Skill 代码并返回因子数据 */
export async function runSkill(
  code: string,
  symbol: string,
  startDate: string,
  endDate: string,
  freq: Freq,
  options?: { include_news?: boolean; include_financials?: boolean },
): Promise<SkillRunResponse> {
  const token = getToken()
  const response = await fetch(`${BASE_URL}/api/v1/skills/run`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      code, symbol, start_date: startDate, end_date: endDate, freq,
      include_news: options?.include_news ?? false,
      include_financials: options?.include_financials ?? false,
    }),
  })
  if (!response.ok) {
    const json = await response.json().catch(() => null)
    const detail = json?.detail ?? response.statusText
    throw new Error(`Skill 执行失败 (${response.status}): ${detail}`)
  }
  return response.json()
}

export interface SymbolSuggestion {
  symbol: string
  name: string
  exchange: string
}

/** 美股 symbol 联想搜索（后端代理 FMP，Redis 缓存 24h） */
export async function searchSymbol(q: string, limit = 10): Promise<SymbolSuggestion[]> {
  const trimmed = q.trim()
  if (!trimmed) return []
  const resp = await client.get('/api/v1/skills/symbol-search', {
    params: { q: trimmed, limit },
  })
  return resp.data
}

// ── Gallery/Mine API ───────────────────────────────────────────────────────────

export async function getGallery() {
  const resp = await client.get('/api/v1/skills/gallery')
  return resp.data
}

export async function getMine() {
  const resp = await client.get('/api/v1/skills/mine')
  return resp.data
}

export async function getSkillDetail(id: string) {
  const resp = await client.get(`/api/v1/skills/${id}`)
  return resp.data
}

export interface SaveSkillPayload {
  title: string
  description: string
  category: string
  code: string
  symbol: string
  start_date: string
  end_date: string
  freq: 'daily' | 'weekly'
}

export async function saveSkill(payload: SaveSkillPayload) {
  const resp = await client.post('/api/v1/skills/save', payload)
  return resp.data
}

export interface RerunPayload {
  symbol: string
  start_date: string
  end_date: string
  freq: 'daily' | 'weekly'
}

export interface RerunResult {
  cached: boolean
  snapshot: Record<string, unknown>
  narrative: Record<string, unknown> | null
}

export async function rerunSkill(id: string, payload: RerunPayload) {
  const resp = await client.post(`/api/v1/skills/${id}/rerun`, payload)
  return resp.data
}

export async function deleteSkill(id: string) {
  await client.delete(`/api/v1/skills/${id}`)
}
