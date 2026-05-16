import apiClient from './client'

export interface SectorPERecord {
  date: string
  pe: number
}

export interface SectorValuation {
  sector: string
  sector_cn: string
  etf_symbol: string
  current_pe: number | null
  hist_mean: number | null
  hist_std: number | null
  z_score: number | null
  label: string
  label_en: string
  hist_pe: SectorPERecord[]
  data_quarters: number
}

export interface SectorValuationResponse {
  as_of: string
  sectors: SectorValuation[]
}

export const fetchSectorValuations = async (): Promise<SectorValuationResponse> => {
  const response = await apiClient.get<SectorValuationResponse>('/api/v1/valuation/sectors')
  return response.data
}
