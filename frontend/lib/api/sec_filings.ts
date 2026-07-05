// frontend/lib/api/sec_filings.ts
import apiClient from './client'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export interface EightKItem {
  code: string
  label: string
}

export interface FilingRecord {
  form: string
  form_name: string
  form_desc: string
  category: string
  filing_date: string
  report_date: string
  accession_number: string
  primary_doc_description: string
  items: EightKItem[]
  index_url: string
  doc_url: string
}

export interface FilingCategory {
  key: string
  label: string
  label_en: string
  count: number
  filings: FilingRecord[]
}

export interface CompanyInfo {
  cik: string
  name: string
  tickers: string[]
  exchanges: string[]
  sic_description: string
}

export interface CompanyFilingsResponse {
  request_id: string
  company: CompanyInfo
  total: number
  categories: FilingCategory[]
}

export async function fetchCompanyFilings(
  query: string
): Promise<CompanyFilingsResponse> {
  const { data } = await apiClient.get<CompanyFilingsResponse>('/api/v1/sec/filings', {
    params: { query },
    timeout: 60000, // SEC 溢出文件抓取可能较慢
  })
  return data
}

export interface FilingDocument {
  seq: string
  type: string
  label: string
  description: string
  filename: string
  url: string
  highlight: boolean
}

export interface FilingDocumentsResponse {
  request_id: string
  accession: string
  index_url: string
  documents: FilingDocument[]
}

export async function fetchFilingDocuments(
  cik: string,
  accession: string
): Promise<FilingDocumentsResponse> {
  const { data } = await apiClient.get<FilingDocumentsResponse>('/api/v1/sec/filing-documents', {
    params: { cik, accession },
    timeout: 30000,
  })
  return data
}

export interface ProductItem {
  name: string
  explanation: string
  market_share: string
}

export interface CompanyProfile {
  one_liner: string
  industry: string
  supply_chain_position: string
  main_products: ProductItem[]
  main_customers: string[]
  moat_rating: '宽' | '中' | '窄' | '无'
  moat_reason: string
  differentiation: string
  competitors: string[]
}

export interface CompanyProfileResponse {
  request_id: string
  cik: string
  name: string
  ticker: string
  sic_description: string
  profile: CompanyProfile
}

export type CompanyProfileStreamEvent =
  | {
      event: 'start' | 'meta' | 'generating'
      message: string
      company?: Partial<CompanyProfileResponse>
      done?: false
    }
  | {
      event: 'resolved' | 'cache_hit'
      message: string
      company: Partial<CompanyProfileResponse>
      done?: false
    }
  | {
      event: 'done'
      data: CompanyProfileResponse
      done: true
    }
  | {
      event: 'error'
      message: string
      done: true
    }

export async function fetchCompanyProfile(
  query: string
): Promise<CompanyProfileResponse> {
  const { data } = await apiClient.get<CompanyProfileResponse>('/api/v1/sec/company-profile', {
    params: { query },
    timeout: 60000, // 大模型生成可能较慢
  })
  return data
}

export async function* streamCompanyProfile(
  query: string,
  signal?: AbortSignal,
): AsyncGenerator<CompanyProfileStreamEvent> {
  const params = new URLSearchParams({ query })
  const headers: HeadersInit = { Accept: 'text/event-stream' }
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token')
    if (token) headers.Authorization = `Bearer ${token}`
  }

  const response = await fetch(`${API_BASE_URL}/api/v1/sec/company-profile/stream?${params.toString()}`, {
    headers,
    signal,
  })

  if (!response.ok) {
    throw new Error(`公司概览生成失败 (${response.status})`)
  }
  if (!response.body) {
    throw new Error('浏览器不支持流式响应')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() ?? ''

    for (const chunk of chunks) {
      const dataLine = chunk
        .split('\n')
        .find((line) => line.startsWith('data: '))
      if (!dataLine) continue
      yield JSON.parse(dataLine.slice(6)) as CompanyProfileStreamEvent
    }
  }

  buffer += decoder.decode()
  if (buffer.trim()) {
    const dataLine = buffer
      .split('\n')
      .find((line) => line.startsWith('data: '))
    if (dataLine) {
      yield JSON.parse(dataLine.slice(6)) as CompanyProfileStreamEvent
    }
  }
}
