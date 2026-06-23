import apiClient from './client'

export interface PanicPoint {
  date: string
  rsi: number
  panic: number
}

export interface SectorPanic {
  sector_cn: string
  sector: string
  symbol: string
  current_rsi: number | null
  current_panic: number | null
  history: PanicPoint[]
}

export interface IndustryPanicResponse {
  as_of: string
  sectors: SectorPanic[]
}

export async function fetchIndustryPanic(): Promise<IndustryPanicResponse> {
  const { data } = await apiClient.get<IndustryPanicResponse>('/api/v1/industry-panic')
  return data
}
