// frontend/lib/api/sec_filings.ts
import apiClient from './client'

export interface EightKItem {
  code: string
  label: string
}

export interface FilingRecord {
  form: string
  form_name: string
  form_desc: string
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

export interface FilingDocument {
  seq: string
  type: string
  label: string
  description: string
  filename: string
  url: string
  highlight: boolean
}

export interface FilingDocumentsResponse {
  request_id: string
  accession: string
  index_url: string
  documents: FilingDocument[]
}

export async function fetchFilingDocuments(
  cik: string,
  accession: string
): Promise<FilingDocumentsResponse> {
  const { data } = await apiClient.get<FilingDocumentsResponse>('/api/v1/sec/filing-documents', {
    params: { cik, accession },
    timeout: 30000,
  })
  return data
}

export interface CompanyProfile {
  one_liner: string
  industry: string
  supply_chain_position: string
  main_products: string[]
  main_customers: string[]
  differentiation: string
  competitors: string[]
}

export interface CompanyProfileResponse {
  request_id: string
  cik: string
  name: string
  ticker: string
  sic_description: string
  profile: CompanyProfile
}

export async function fetchCompanyProfile(
  query: string
): Promise<CompanyProfileResponse> {
  const { data } = await apiClient.get<CompanyProfileResponse>('/api/v1/sec/company-profile', {
    params: { query },
    timeout: 60000, // 大模型生成可能较慢
  })
  return data
}
