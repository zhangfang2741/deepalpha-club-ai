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

export interface LeaderboardEntry {
  symbol: string
  name: string
  composite_score: number
  coverage: number
  confidence: string
  top_state: SignalState | null
  states: SignalState[]
  dimension_scores: Record<string, number>
}

export interface LeaderboardResponse {
  request_id: string
  status: string
  as_of: string
  computed_at: string
  universe_source: string
  universe_size: number
  scanned: number
  note: string
  entries: LeaderboardEntry[]
}

export async function fetchLeaderboard(): Promise<LeaderboardResponse> {
  const { data } = await apiClient.get<LeaderboardResponse>(
    '/api/v1/institutional-signals/leaderboard',
    { timeout: 90000 }, // 首次扫描 universe 较慢，给足 90s
  )
  return data
}
