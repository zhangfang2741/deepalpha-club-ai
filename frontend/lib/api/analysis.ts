/**
 * API functions for stock analysis
 */

import apiClient from './client'

export interface AnalysisLayer {
  score: number
  summary: string
  key_findings: string[]
  confidence: number
}

export interface AnalysisDataPoint {
  value: string | number
  label: string
  source: string
  url?: string
  fetched_at: string
}

export interface AnalysisResponse {
  ticker: string
  company_name: string
  final_score: number
  recommendation: 'BUY' | 'HOLD' | 'SELL' | 'ERROR'
  risk_reward_ratio: number
  position_recommendation: string
  layers: Record<string, AnalysisLayer>
  sources: AnalysisDataPoint[]
  analysis_timestamp: string
  analysis_duration_seconds?: number
}

export async function analyzeStock(
  ticker: string,
  includeIndustry: boolean = true,
  includeSentiment: boolean = true
): Promise<AnalysisResponse> {
  const response = await apiClient.post<AnalysisResponse>('/api/v1/analysis/stock', {
    ticker: ticker.toUpperCase(),
    include_industry: includeIndustry,
    include_sentiment: includeSentiment,
  })

  return response.data
}

export async function getStockAnalysis(
  ticker: string,
  includeIndustry: boolean = true,
  includeSentiment: boolean = true
): Promise<AnalysisResponse> {
  const params = {
    include_industry: includeIndustry,
    include_sentiment: includeSentiment,
  }
  
  const response = await apiClient.get<AnalysisResponse>(`/api/v1/analysis/stock/${ticker.toUpperCase()}`, {
    params
  })

  return response.data
}

export async function getAvailableLayers(): Promise<{
  layers: Array<{
    name: string
    display_name: string
    description: string
    weight: number
  }>
  recommendations: Record<string, string>
}> {
  const response = await apiClient.get('/api/v1/analysis/layers')
  return response.data
}

export async function checkAnalysisHealth(): Promise<{ status: string; service: string }> {
  const response = await apiClient.get('/api/v1/analysis/health')
  return response.data
}