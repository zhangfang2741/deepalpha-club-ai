import apiClient from './client'

export interface TranscriptCandidate {
  request_id: string
  title: string
  url: string
  published_at: string | null
}

export interface TranscriptSegment {
  request_id: string
  speaker: string | null
  text: string
  section: 'prepared_remarks' | 'questions_and_answers'
}

export interface TranscriptListResponse {
  request_id: string
  ticker: string
  source: string
  transcripts: TranscriptCandidate[]
}

export interface TranscriptDetailResponse {
  request_id: string
  ticker: string
  title: string
  url: string
  source: string
  published_date: string | null
  prepared_remarks: string
  questions_and_answers: string
  segments: TranscriptSegment[]
  candidates: TranscriptCandidate[]
}

export async function fetchTranscriptList(
  ticker: string,
  limit: number = 8
): Promise<TranscriptListResponse> {
  const response = await apiClient.get<TranscriptListResponse>(
    `/api/v1/transcripts/${ticker.toUpperCase()}`,
    { params: { limit } }
  )
  return response.data
}

export async function fetchTranscriptDetail(
  ticker: string,
  url: string
): Promise<TranscriptDetailResponse> {
  const response = await apiClient.get<TranscriptDetailResponse>(
    `/api/v1/transcripts/${ticker.toUpperCase()}/detail`,
    { params: { url } }
  )
  return response.data
}
