import apiClient from './client'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export interface TranscriptCandidate {
  request_id: string
  title: string
  url: string
  published_at: string | null
}

export interface TranscriptSegment {
  request_id: string
  speaker: string | null
  text: string
  section: 'prepared_remarks' | 'questions_and_answers'
}

export interface TranscriptListResponse {
  request_id: string
  ticker: string
  source: string
  transcripts: TranscriptCandidate[]
}

export interface TranscriptDetailResponse {
  request_id: string
  ticker: string
  title: string
  url: string
  source: string
  published_date: string | null
  prepared_remarks: string
  questions_and_answers: string
  segments: TranscriptSegment[]
  candidates: TranscriptCandidate[]
}

export async function fetchTranscriptList(
  ticker: string,
  limit: number = 8
): Promise<TranscriptListResponse> {
  const response = await apiClient.get<TranscriptListResponse>(
    `/api/v1/transcripts/${ticker.toUpperCase()}`,
    { params: { limit } }
  )
  return response.data
}

export async function fetchTranscriptDetail(
  ticker: string,
  url: string
): Promise<TranscriptDetailResponse> {
  const response = await apiClient.get<TranscriptDetailResponse>(
    `/api/v1/transcripts/${ticker.toUpperCase()}/detail`,
    { params: { url } }
  )
  return response.data
}

export interface TranscriptSummary {
  overview: string
  key_points: string[]
  financial_highlights: string[]
  guidance: string
  qa_highlights: string[]
  risks: string[]
}

export interface TranscriptSummaryResponse {
  request_id: string
  ticker: string
  title: string
  url: string
  summary: TranscriptSummary
}

export interface TranscriptTranslationResponse {
  request_id: string
  ticker: string
  url: string
  prepared_remarks_zh: string
  questions_and_answers_zh: string
}

export async function fetchTranscriptSummary(
  detail: TranscriptDetailResponse
): Promise<TranscriptSummaryResponse> {
  const response = await apiClient.post<TranscriptSummaryResponse>(
    '/api/v1/transcripts/summarize',
    {
      ticker: detail.ticker,
      title: detail.title,
      url: detail.url,
      prepared_remarks: detail.prepared_remarks,
      questions_and_answers: detail.questions_and_answers,
    },
    // 总结是一次性大调用（长原文 + 结构化输出 + thinking），后端预算 100s，
    // 前端需高于后端预算，覆盖默认的 30s，避免前端提前超时
    { timeout: 120000 }
  )
  return response.data
}

export async function fetchTranscriptTranslation(
  detail: TranscriptDetailResponse
): Promise<TranscriptTranslationResponse> {
  const response = await apiClient.post<TranscriptTranslationResponse>(
    '/api/v1/transcripts/translate',
    {
      ticker: detail.ticker,
      url: detail.url,
      prepared_remarks: detail.prepared_remarks,
      questions_and_answers: detail.questions_and_answers,
    }
  )
  return response.data
}

export type TranslationSection = 'prepared_remarks' | 'questions_and_answers'

export interface TranslationStreamEvent {
  section: TranslationSection | null
  text: string
  done: boolean
  error?: string
}

export async function* streamTranscriptTranslation(
  detail: TranscriptDetailResponse,
  signal?: AbortSignal
): AsyncGenerator<TranslationStreamEvent> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
  const resp = await fetch(`${BASE_URL}/api/v1/transcripts/translate/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      ticker: detail.ticker,
      url: detail.url,
      prepared_remarks: detail.prepared_remarks,
      questions_and_answers: detail.questions_and_answers,
    }),
    signal,
  })

  if (!resp.ok) throw new Error(`请求失败 (${resp.status})`)

  const reader = resp.body?.getReader()
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
          yield JSON.parse(line.slice(6)) as TranslationStreamEvent
        } catch {
          // 忽略不完整/异常行
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
