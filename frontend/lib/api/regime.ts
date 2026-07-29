// frontend/lib/api/regime.ts
import apiClient from './client'

export interface RegimePoint {
  trade_date: string
  qqq_return: number | null
  realized_vol: number | null
  vix: number | null
  ods: number | null
  cf: number | null
  obv_slope: number | null
  cmf: number | null
  p_risk_on: number | null
  p_neutral: number | null
  p_risk_off: number | null
  regime_label: string | null
  confirmed_label: string | null
  params_version: string | null
  factor_weight: number | null
}

export interface RegimeResponse {
  request_id: string
  latest: RegimePoint | null
  history: RegimePoint[]
}

export interface RegimeStageResult {
  request_id: string
  rows: number
  written: number
  latest_date: string | null
  latest_label: string | null
  latest_factor_weight: number | null
}

// 状态标签中文映射
export const REGIME_LABEL_ZH: Record<string, string> = {
  risk_on: '逐利',
  neutral: '观望',
  risk_off: '避险',
}

export async function fetchRegime(limit = 250): Promise<RegimeResponse> {
  const { data } = await apiClient.get<RegimeResponse>('/api/v1/regime', {
    params: { limit },
  })
  return data
}

export async function triggerRegimeStage(
  lookbackDays = 1400
): Promise<RegimeStageResult> {
  const { data } = await apiClient.post<RegimeStageResult>(
    '/api/v1/regime/run',
    null,
    { params: { lookback_days: lookbackDays }, timeout: 120000 }
  )
  return data
}
