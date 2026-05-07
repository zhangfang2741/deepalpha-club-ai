// frontend/lib/api/fear_greed.ts
import apiClient from './client'

export interface FearGreedPoint {
  date: string
  score: number
  rating: string
}

export interface FearGreedSnapshot {
  score: number
  rating: string
  date?: string
}

export interface FearGreedResponse {
  request_id: string
  current: FearGreedSnapshot
  previous_week: FearGreedSnapshot
  previous_month: FearGreedSnapshot
  previous_year: FearGreedSnapshot
  history_low: FearGreedSnapshot
  history_high: FearGreedSnapshot
  history: FearGreedPoint[]
}

export async function fetchFearGreed(): Promise<FearGreedResponse> {
  const { data } = await apiClient.get<FearGreedResponse>('/api/v1/fear-greed')
  return data
}
