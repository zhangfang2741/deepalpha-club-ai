import apiClient from './client'

export interface Candle {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface TradingRange {
  kind: 'accumulation' | 'distribution'
  support: number
  resistance: number
  start_time: string
  end_time: string
}

export interface WyckoffEvent {
  code: string
  name: string
  time: string
  price: number
  volume_ratio: number
  phase: string
  description: string
}

export interface WyckoffLaw {
  key: 'supply_demand' | 'cause_effect' | 'effort_result'
  name: string
  verdict: string
  detail: string
}

export interface WyckoffPhase {
  stage: string
  stage_label: string
  phase: string
  phase_label: string
  breakout: 'up' | 'down' | 'none'
}

export interface Recommendation {
  action: string
  action_label: string
  bias: 'bullish' | 'bearish' | 'neutral'
  reasons: string[]
  caveats: string[]
}

export interface WyckoffAnalysisResult {
  symbol: string
  bars_count: number
  context: string
  candles: Candle[]
  trading_range: TradingRange | null
  events: WyckoffEvent[]
  phase: WyckoffPhase | null
  laws: WyckoffLaw[]
  stage_label: string
  position_desc: string
  summary: string
  recommendation: Recommendation | null
}

export async function fetchWyckoffAnalysis(
  symbol: string,
  startDate: string,
  endDate: string,
  freq = 'daily',
): Promise<WyckoffAnalysisResult> {
  const res = await apiClient.get<WyckoffAnalysisResult>('/api/v1/wyckoff/analysis', {
    params: { symbol, start_date: startDate, end_date: endDate, freq },
  })
  return res.data
}
