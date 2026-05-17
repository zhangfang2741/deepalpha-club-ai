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

export interface ETFValuationSummaryItem {
  symbol: string
  name: string
  sector_key: string
  sector_cn: string
  current_pe: number | null
  hist_mean: number | null
  hist_std: number | null
  z_score: number | null
  label: string
  label_en: string
  data_quarters: number
}

export interface ETFValuationSummaryResponse {
  as_of: string
  etfs: ETFValuationSummaryItem[]
}

export interface ETFValuationDetail {
  symbol: string
  name: string
  current_pe: number | null
  hist_mean: number | null
  hist_std: number | null
  z_score: number | null
  label: string
  label_en: string
  hist_pe: SectorPERecord[]
  data_quarters: number
}

export const fetchETFSummary = async (): Promise<ETFValuationSummaryResponse> => {
  const response = await apiClient.get<ETFValuationSummaryResponse>('/api/v1/valuation/etf-summary')
  return response.data
}

export const fetchETFDetail = async (symbol: string): Promise<ETFValuationDetail> => {
  const response = await apiClient.get<ETFValuationDetail>('/api/v1/valuation/etf-detail', {
    params: { symbol },
  })
  return response.data
}

export interface IndustryValuation {
  industry: string
  industry_cn: string
  current_pe: number | null
  hist_mean: number | null
  hist_std: number | null
  z_score: number | null
  label: string
  label_en: string
  hist_pe: SectorPERecord[]
  data_quarters: number
}

export interface SectorWithIndustries {
  sector: string
  sector_cn: string
  current_pe: number | null
  hist_mean: number | null
  hist_std: number | null
  z_score: number | null
  label: string
  label_en: string
  hist_pe: SectorPERecord[]
  data_quarters: number
  industries: IndustryValuation[]
}

export interface GICSValuationResponse {
  as_of: string
  sectors: SectorWithIndustries[]
}

export const fetchGICSValuations = async (): Promise<GICSValuationResponse> => {
  const response = await apiClient.get<GICSValuationResponse>('/api/v1/valuation/gics')
  return response.data
}
