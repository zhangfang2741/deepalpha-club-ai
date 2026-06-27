const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export interface EvidenceItem {
  snippet: string
  source: string
}

export interface UnderstandIndustryData {
  description: string
  main_products: string[]
  key_customers: string[]
  development_stage: string
  what: string
  why: string
  evidence: EvidenceItem[]
}

export interface WhyItExistsData {
  tech_drivers: string[]
  policy_drivers: string[]
  demand_drivers: string[]
  cost_drivers: string[]
  what: string
  why: string
  evidence: EvidenceItem[]
}

export interface ChainLevel {
  level: string
  description: string
  key_players: string[]
}

export interface IndustryChainData {
  upstream: ChainLevel
  midstream: ChainLevel
  downstream: ChainLevel
  what: string
  why: string
  evidence: EvidenceItem[]
}

export interface KeyBottlenecksData {
  bottlenecks: string[]
  pricing_power: string
  most_profitable_segment: string
  what: string
  why: string
  evidence: EvidenceItem[]
}

export interface LeadingCompany {
  name: string
  ticker?: string
  business: string
  moat: string
}

export interface LeadingCompaniesData {
  companies: LeadingCompany[]
  what: string
  why: string
  evidence: EvidenceItem[]
}

export interface BusinessModelData {
  revenue_model: string
  cost_structure: string
  profit_drivers: string
  moat_sources: string[]
  what: string
  why: string
  evidence: EvidenceItem[]
}

export interface InvestmentViewData {
  opportunities: string[]
  risks: string[]
  focus_areas: string[]
  conclusion: string
  what: string
  why: string
  evidence: EvidenceItem[]
}

export type ResearchStepData =
  | UnderstandIndustryData
  | WhyItExistsData
  | IndustryChainData
  | KeyBottlenecksData
  | LeadingCompaniesData
  | BusinessModelData
  | InvestmentViewData

export interface ResearchStepEvent {
  event: 'step'
  step_index: number
  step_key: string
  step_label: string
  data: ResearchStepData
  done: false
}

export interface ResearchErrorEvent {
  event: 'error'
  step_index: number | null
  step_key: string | null
  message: string
  done: false
}

export interface ResearchDoneEvent {
  event: 'done'
  industry: string
  total_steps: number
  done: true
}

export type ResearchSSEEvent = ResearchStepEvent | ResearchErrorEvent | ResearchDoneEvent

export async function* streamIndustryResearch(
  industry: string,
  signal?: AbortSignal,
): AsyncGenerator<ResearchSSEEvent> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
  const resp = await fetch(`${BASE_URL}/api/v1/research/industry`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ industry }),
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
          yield JSON.parse(line.slice(6)) as ResearchSSEEvent
        } catch {
          // ignore malformed lines
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
