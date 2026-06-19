import apiClient from './client'

export interface UpgradeStock {
  symbol: string
  name: string
  sector: string
  last_month_target: number
  last_quarter_target: number
  last_year_target: number
  all_time_target: number
  last_month_count: number
  month_mom: number
  quarter_yoy: number
  year_vs_all: number
}

export interface Nasdaq100UpgradesResponse {
  as_of: string
  total_constituents: number
  upgrade_count: number
  stocks: UpgradeStock[]
}

export interface PriceTargetPoint {
  label: string
  avg_target: number
  count: number
}

export interface PriceTargetHistoryResponse {
  symbol: string
  points: PriceTargetPoint[]
}

export async function fetchNasdaq100Upgrades(): Promise<Nasdaq100UpgradesResponse> {
  const res = await apiClient.get<Nasdaq100UpgradesResponse>('/api/v1/analyst-upgrades/nasdaq100')
  return res.data
}

export async function fetchPriceTargetHistory(symbol: string): Promise<PriceTargetHistoryResponse> {
  const res = await apiClient.get<PriceTargetHistoryResponse>(
    `/api/v1/analyst-upgrades/price-target-history/${symbol}`
  )
  return res.data
}
