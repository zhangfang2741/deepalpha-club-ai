import apiClient from './client'
import { BASE_URL } from './client'

export type GraphProperty = { name: string; value: unknown }
export type SupplyNode = { nodeId: string; nodeType: string; properties: GraphProperty[] }
export type SupplyEdge = { edgeId: string; srcId: string; dstId: string; edgeType: string; properties: GraphProperty[] }
export type SupplyGraph = { nodes: SupplyNode[]; edges: SupplyEdge[]; truncated?: boolean }

export type SupplyRun = {
  id: string
  run_type: string
  universe: string
  status: string
  total: number
  completed: number
  failed: number
  params: Record<string, unknown>
  quota_paused_at: string | null
  resume_after: string | null
  probe_attempts: number
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

export type SupplyTask = {
  id: string
  run_id: string
  ticker: string
  stage: string
  status: string
  retries: number
  max_retries: number
  quota_retries: number
  celery_task_id: string | null
  error: string | null
  resume_after: string | null
  result_summary: Record<string, unknown>
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

export type SupplyRunDetail = { run: SupplyRun; tasks: SupplyTask[] }

export type WorkerStatus = { online: boolean; count: number; workers: string[]; error?: string }
export type PreviewEvent =
  | { type: 'status'; content: string }
  | { type: 'delta'; content: string }
  | { type: 'result'; graph: SupplyGraph }
  | { type: 'error'; message: string }

const streamPreview = async (
  ticker: string,
  onEvent: (event: PreviewEvent) => void,
  signal?: AbortSignal,
) => {
  const token = typeof window === 'undefined' ? null : localStorage.getItem('access_token')
  const response = await fetch(
    `${BASE_URL}/api/v1/supply-graph/preview/stream?ticker=${encodeURIComponent(ticker)}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : undefined, signal },
  )
  if (!response.ok || !response.body) throw new Error(`实时分析请求失败（${response.status}）`)
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''
    for (const frame of frames) {
      const data = frame
        .split('\n')
        .find((line) => line.startsWith('data: '))
        ?.slice(6)
      if (data) onEvent(JSON.parse(data) as PreviewEvent)
    }
    if (done) break
  }
}

export const supplyGraphApi = {
  previewStream: streamPreview,
  graph: async (ticker: string, depth = 1, direction = 'both') =>
    (await apiClient.get<SupplyGraph>('/api/v1/supply-graph/graph', { params: { ticker, depth, direction }, timeout: 30000 })).data,
  expand: async (nodeId: string, depth = 1, direction = 'both') =>
    (await apiClient.get<SupplyGraph>('/api/v1/supply-graph/graph/expand', { params: { from_node_id: nodeId, depth, direction }, timeout: 30000 })).data,
  runCompany: async (ticker: string) => (await apiClient.post(`/api/v1/supply-graph/companies/${ticker}/run`)).data,
  createRun: async (universe: string, params: Record<string, unknown> = {}) =>
    (await apiClient.post('/api/v1/supply-graph/runs', { universe, params })).data,
  workerStatus: async () =>
    (await apiClient.get<WorkerStatus>('/api/v1/supply-graph/worker-status', { timeout: 5000 })).data,
  runs: async () => (await apiClient.get<SupplyRun[]>('/api/v1/supply-graph/runs')).data,
  run: async (id: string) => (await apiClient.get<SupplyRunDetail>(`/api/v1/supply-graph/runs/${id}`)).data,
  pauseRun: async (id: string) => (await apiClient.post(`/api/v1/supply-graph/runs/${id}/pause`)).data,
  resumeRun: async (id: string) => (await apiClient.post(`/api/v1/supply-graph/runs/${id}/resume`)).data,
  retryFailed: async (id: string) => (await apiClient.post(`/api/v1/supply-graph/runs/${id}/retry-failed`)).data,
  restartRun: async (id: string) => (await apiClient.post(`/api/v1/supply-graph/runs/${id}/restart`)).data,
  deleteRun: async (id: string) => (await apiClient.delete(`/api/v1/supply-graph/runs/${id}`)).data,
  clues: async (edgeId: string) => (await apiClient.get(`/api/v1/supply-graph/edges/${edgeId}/clues`)).data,
}
