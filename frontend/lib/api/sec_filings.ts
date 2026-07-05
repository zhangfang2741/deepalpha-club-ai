// frontend/lib/api/sec_filings.ts
import apiClient from './client'

export interface EightKItem {
  code: string
  label: string
}

export interface FilingRecord {
  form: string
  category: string
  filing_date: string
  report_date: string
  accession_number: string
  primary_doc_description: string
  items: EightKItem[]
  index_url: string
  doc_url: string
}

export interface FilingCategory {
  key: string
  label: string
  label_en: string
  count: number
  filings: FilingRecord[]
}

export interface CompanyInfo {
  cik: string
  name: string
  tickers: string[]
  exchanges: string[]
  sic_description: string
}

export interface CompanyFilingsResponse {
  request_id: string
  company: CompanyInfo
  total: number
  categories: FilingCategory[]
}

export async function fetchCompanyFilings(
  query: string
): Promise<CompanyFilingsResponse> {
  const { data } = await apiClient.get<CompanyFilingsResponse>('/api/v1/sec/filings', {
    params: { query },
    timeout: 60000, // SEC 溢出文件抓取可能较慢
  })
  return data
}
