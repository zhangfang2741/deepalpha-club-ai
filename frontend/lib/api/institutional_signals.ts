import apiClient from './client'

export interface SignalItem {
  key: string
  label: string
  value: string | null
  direction: 'up' | 'down' | 'flat'
  hit: boolean
  detail: string | null
}

export interface DimensionScore {
  key: string
  label: string
  question: string
  score: number
  status: 'ok' | 'partial' | 'unavailable'
  signals: SignalItem[]
}

export interface SignalState {
  key: string
  emoji: string
  label: string
  stars: number
  meaning: string
  evidence: string[]
}

export interface InstitutionalSignalReport {
  request_id: string
  symbol: string
  name: string
  as_of: string
  composite_score: number
  coverage: number
  coverage_total: number
  confidence: string
  headline: string
  dimensions: DimensionScore[]
  states: SignalState[]
}

export async function fetchInstitutionalSignals(
  symbol: string,
): Promise<InstitutionalSignalReport> {
  const { data } = await apiClient.get<InstitutionalSignalReport>(
    '/api/v1/institutional-signals',
    { params: { symbol }, timeout: 30000 },
  )
  return data
}
