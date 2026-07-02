import apiClient from './client'

export interface PriceTargetPoint {
  label: string
  avg_target: number
  count: number
}

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
  recent_points: PriceTargetPoint[]
}

export interface Nasdaq100UpgradesResponse {
  as_of: string
  total_constituents: number
  upgrade_count: number
  stocks: UpgradeStock[]
}

export interface SP500UpgradesResponse {
  as_of: string
  total_constituents: number
  upgrade_count: number
  stocks: UpgradeStock[]
}

export interface PriceTargetHistoryResponse {
  symbol: string
  points: PriceTargetPoint[]
}

export async function fetchNasdaq100Upgrades(refresh = false): Promise<Nasdaq100UpgradesResponse> {
  const res = await apiClient.get<Nasdaq100UpgradesResponse>('/api/v1/analyst-upgrades/nasdaq100', {
    params: refresh ? { refresh: true } : undefined,
  })
  return res.data
}

export async function fetchSP500Upgrades(refresh = false): Promise<SP500UpgradesResponse> {
  const res = await apiClient.get<SP500UpgradesResponse>('/api/v1/analyst-upgrades/sp500', {
    params: refresh ? { refresh: true } : undefined,
  })
  return res.data
}

export async function fetchPriceTargetHistory(symbol: string): Promise<PriceTargetHistoryResponse> {
  const res = await apiClient.get<PriceTargetHistoryResponse>(
    `/api/v1/analyst-upgrades/price-target-history/${symbol}`
  )
  return res.data
}

export async function fetchCustomPriceTargetHistory(
  symbol: string,
  start: string,
  end: string,
): Promise<PriceTargetHistoryResponse> {
  const res = await apiClient.get<PriceTargetHistoryResponse>(
    '/api/v1/analyst-upgrades/custom-price-target',
    { params: { symbol, start, end } },
  )
  return res.data
}
