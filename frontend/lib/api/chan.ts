import apiClient from './client'

export interface MergedCandle {
  idx: number
  time: string
  high: number
  low: number
  open: number
  close: number
}

export interface Fractal {
  type: 'top' | 'bottom'
  time: string
  price: number
  idx: number
  confirmed: boolean
}

export interface Stroke {
  direction: 'up' | 'down'
  start_time: string
  end_time: string
  start_price: number
  end_price: number
  high: number
  low: number
  confirmed: boolean
}

export interface Segment {
  direction: 'up' | 'down'
  start_time: string
  end_time: string
  start_price: number
  end_price: number
  high: number
  low: number
  stroke_count: number
  confirmed: boolean
}

export interface Pivot {
  zg: number
  zd: number
  gg: number
  dd: number
  start_time: string
  end_time: string
  level: 'stroke' | 'segment'
  confirmed: boolean
}

export interface MACDData {
  times: string[]
  dif: number[]
  dea: number[]
  bar: number[]
}

export interface Signal {
  type: 'buy1' | 'buy2' | 'buy3' | 'sell1' | 'sell2' | 'sell3'
  label: string
  time: string
  price: number
  strength: 'strong' | 'medium' | 'weak'
  is_buy: boolean
  description: string
  area_ratio: number | null
  confirmed: boolean
}

export interface Recommendation {
  action: string
  action_label: string
  bias: 'bullish' | 'bearish' | 'neutral'
  reasons: string[]
  caveats: string[]
}

export interface ChanAnalysisResult {
  symbol: string
  bars_count: number
  merged_candles: MergedCandle[]
  fractals: Fractal[]
  strokes: Stroke[]
  segments: Segment[]
  stroke_pivots: Pivot[]
  segment_pivots: Pivot[]
  macd: MACDData | null
  signals: Signal[]
  current_trend: string
  summary: string
  recommendation: Recommendation | null
  pending_notes: string[]
}

export type GapDirection = 'price_lags_industry' | 'price_ahead_of_fundamentals' | 'unclear'

export interface GapItem {
  dimension: string
  market_says: string
  industry_says: string
  direction: GapDirection
  interpretation: string
}

export interface StructureGapResult {
  symbol: string
  aligned: string[]
  gaps: GapItem[]
  key_question: string
  caveats: string[]
}

export async function fetchStructureGap(
  symbol: string,
  startDate: string,
  endDate: string,
  industryView: string,
  freq = 'daily',
): Promise<StructureGapResult> {
  const res = await apiClient.post<StructureGapResult>('/api/v1/chan/gap', {
    symbol,
    start_date: startDate,
    end_date: endDate,
    industry_view: industryView,
    freq,
  })
  return res.data
}

export async function fetchChanAnalysis(
  symbol: string,
  startDate: string,
  endDate: string,
  freq = 'daily',
): Promise<ChanAnalysisResult> {
  const res = await apiClient.get<ChanAnalysisResult>('/api/v1/chan/analysis', {
    params: { symbol, start_date: startDate, end_date: endDate, freq },
  })
  return res.data
}
