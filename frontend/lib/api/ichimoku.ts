import apiClient from './client'

export interface Candle {
  time: string
  open: number
  high: number
  low: number
  close: number
}

export interface LinePoint {
  time: string
  value: number
}

export interface IchimokuSignal {
  type: 'tk_golden' | 'tk_dead' | 'kumo_up' | 'kumo_down'
  label: string
  time: string
  price: number
  strength: 'strong' | 'medium' | 'weak'
  is_buy: boolean
  description: string
}

export interface IchimokuState {
  price: number
  price_vs_cloud: 'above' | 'in' | 'below' | 'na'
  cloud_color: 'bullish' | 'bearish' | 'na'
  tk_relation: 'tenkan_above' | 'tenkan_below' | 'aligned' | 'na'
  chikou_relation: 'above' | 'below' | 'aligned' | 'na'
  tenkan: number | null
  kijun: number | null
  cloud_top: number | null
  cloud_bottom: number | null
}

export interface Recommendation {
  action: string
  action_label: string
  bias: 'bullish' | 'bearish' | 'neutral'
  reasons: string[]
  caveats: string[]
}

export interface IchimokuAnalysisResult {
  symbol: string
  bars_count: number
  conversion_period: number
  base_period: number
  span_b_period: number
  displacement: number
  candles: Candle[]
  tenkan: LinePoint[]
  kijun: LinePoint[]
  senkou_a: LinePoint[]
  senkou_b: LinePoint[]
  chikou: LinePoint[]
  signals: IchimokuSignal[]
  state: IchimokuState | null
  summary: string
  recommendation: Recommendation | null
}

export async function fetchIchimokuAnalysis(
  symbol: string,
  startDate: string,
  endDate: string,
  freq = 'daily',
): Promise<IchimokuAnalysisResult> {
  const res = await apiClient.get<IchimokuAnalysisResult>('/api/v1/ichimoku/analysis', {
    params: { symbol, start_date: startDate, end_date: endDate, freq },
  })
  return res.data
}
