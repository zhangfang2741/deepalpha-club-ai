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

export const fetchETFHeatmap = async (
  granularity: Granularity = 'day',
  days: number = 30
): Promise<HeatmapResponse> => {
  const response = await apiClient.get<HeatmapResponse>('/api/v1/etf/heatmap', {
    params: { granularity, days },
  })
  return response.data
}
