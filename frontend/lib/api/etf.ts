// frontend/lib/api/etf.ts
import apiClient from './client'

export type Granularity = 'day' | 'week' | 'month'

export interface HeatmapCell {
  date: string
  intensity: number | null
}

export interface HeatmapETFRow {
  symbol: string
  name: string
  cells: HeatmapCell[]
}

export interface HeatmapSectorGroup {
  sector: string
  avg_cells: HeatmapCell[]
  etfs: HeatmapETFRow[]
}

export interface HeatmapResponse {
  granularity: Granularity
  days: number
  date_labels: string[]
  sectors: HeatmapSectorGroup[]
}

export interface Candle {
  t: string
  o: number
  h: number
  l: number
  c: number
  v: number
}

export interface CandleResponse {
  symbol: string
  name: string
  candles: Candle[]
}

export const fetchETFCandles = async (
  symbol: string,
  granularity: Granularity = 'day'
): Promise<CandleResponse> => {
  const response = await apiClient.get<CandleResponse>(`/api/v1/etf/${symbol}/candles`, {
    params: { granularity },
  })
  return response.data
}

export const fetchETFHeatmap = async (
  granularity: Granularity = 'day',
  days: number = 30
): Promise<HeatmapResponse> => {
  const response = await apiClient.get<HeatmapResponse>('/api/v1/etf/heatmap', {
    params: { granularity, days },
  })
  return response.data
}
