import apiClient from './client'

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

export const supplyGraphApi = {
  graph: async (ticker: string, depth = 1, direction = 'both') =>
    (await apiClient.get<SupplyGraph>('/api/v1/supply-graph/graph', { params: { ticker, depth, direction }, timeout: 30000 })).data,
  expand: async (nodeId: string, depth = 1, direction = 'both') =>
    (await apiClient.get<SupplyGraph>('/api/v1/supply-graph/graph/expand', { params: { from_node_id: nodeId, depth, direction }, timeout: 30000 })).data,
  runCompany: async (ticker: string) => (await apiClient.post(`/api/v1/supply-graph/companies/${ticker}/run`)).data,
  createRun: async (universe: string, params: Record<string, unknown> = {}) =>
    (await apiClient.post('/api/v1/supply-graph/runs', { universe, params })).data,
  runs: async () => (await apiClient.get<SupplyRun[]>('/api/v1/supply-graph/runs')).data,
  run: async (id: string) => (await apiClient.get<SupplyRunDetail>(`/api/v1/supply-graph/runs/${id}`)).data,
  pauseRun: async (id: string) => (await apiClient.post(`/api/v1/supply-graph/runs/${id}/pause`)).data,
  resumeRun: async (id: string) => (await apiClient.post(`/api/v1/supply-graph/runs/${id}/resume`)).data,
  retryFailed: async (id: string) => (await apiClient.post(`/api/v1/supply-graph/runs/${id}/retry-failed`)).data,
  restartRun: async (id: string) => (await apiClient.post(`/api/v1/supply-graph/runs/${id}/restart`)).data,
  clues: async (edgeId: string) => (await apiClient.get(`/api/v1/supply-graph/edges/${edgeId}/clues`)).data,
}
