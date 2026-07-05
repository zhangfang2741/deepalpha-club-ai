import apiClient from './client'

export interface SignalExplanation {
  inputs: string[]
  formula: string | null
  thresholds: string | null
  conclusion: string | null
  source: string | null
}

export interface SignalItem {
  key: string
  label: string
  value: string | null
  direction: 'up' | 'down' | 'flat'
  hit: boolean
  detail: string | null
  explain: SignalExplanation | null
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
  logic: string | null
  evidence: string[]
  buy_rank: number | null
  buy_timing: string | null
  buy_edge: string | null
  buy_thesis: string | null
}

export interface BuyStage {
  key: string
  emoji: string
  label: string
  timing: string
  edge: string
  thesis: string
  rank: number
  active: boolean
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
  buy_headline: string
  buy_ladder: BuyStage[]
  price_history: number[]
  dimensions: DimensionScore[]
  states: SignalState[]
}

export async function fetchInstitutionalSignals(
  symbol: string,
  refresh: boolean = false,
): Promise<InstitutionalSignalReport> {
  const { data } = await apiClient.get<InstitutionalSignalReport>(
    '/api/v1/institutional-signals',
    { params: { symbol, ...(refresh ? { refresh: true } : {}) }, timeout: 30000 },
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

export async function fetchLeaderboard(
  universe: string = 'sp500',
  refresh: boolean = false,
): Promise<LeaderboardResponse> {
  const { data } = await apiClient.get<LeaderboardResponse>(
    '/api/v1/institutional-signals/leaderboard',
    { params: { universe, ...(refresh ? { refresh: true } : {}) }, timeout: 90000 }, // 首次扫描 universe 较慢，给足 90s
  )
  return data
}
