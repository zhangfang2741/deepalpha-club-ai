import apiClient from './client'

export type GraphProperty = { name: string; value: unknown }
export type SupplyNode = { nodeId: string; nodeType: string; properties: GraphProperty[] }
export type SupplyEdge = { edgeId: string; srcId: string; dstId: string; edgeType: string; properties: GraphProperty[] }
export type SupplyGraph = { nodes: SupplyNode[]; edges: SupplyEdge[]; truncated?: boolean }

export const supplyGraphApi = {
  graph: async (ticker: string, depth = 1, direction = 'both') =>
    (await apiClient.get<SupplyGraph>('/api/v1/supply-graph/graph', { params: { ticker, depth, direction }, timeout: 30000 })).data,
  expand: async (nodeId: string, depth = 1, direction = 'both') =>
    (await apiClient.get<SupplyGraph>('/api/v1/supply-graph/graph/expand', { params: { from_node_id: nodeId, depth, direction }, timeout: 30000 })).data,
  runCompany: async (ticker: string) => (await apiClient.post(`/api/v1/supply-graph/companies/${ticker}/run`)).data,
  runs: async () => (await apiClient.get('/api/v1/supply-graph/runs')).data,
  run: async (id: string) => (await apiClient.get(`/api/v1/supply-graph/runs/${id}`)).data,
  clues: async (edgeId: string) => (await apiClient.get(`/api/v1/supply-graph/edges/${edgeId}/clues`)).data,
}
