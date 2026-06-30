import apiClient from './client'

export type EntityType = 'Company' | 'Product' | 'Technology' | 'Concept' | 'Resource'
export type RelationType = 'HAS_PRODUCT' | 'SUPPLIED_BY' | 'ENABLED_BY' | 'CONSTRAINED_BY'
export type DocumentType = '10-K' | '10-Q' | '8-K' | 'earnings_call' | 'investor_relations'
export type DocumentStatus = 'pending' | 'processing' | 'done' | 'failed'

export interface Entity {
  id: string
  entity_type: EntityType
  name: string
  aliases: string[]
  description: string | null
  ticker: string | null
  created_at: string
}

export interface Fact {
  id: string
  source_entity_id: string
  target_entity_id: string
  source_entity_name: string | null
  target_entity_name: string | null
  source_entity_type: EntityType | null
  target_entity_type: EntityType | null
  relation_type: RelationType
  evidence_text: string
  confidence: number
  event_time: string | null
  ingestion_time: string
  document_url: string | null
  document_section: string | null
  chunk_id: string | null
}

export interface GraphNode {
  id: string
  name: string
  entity_type: EntityType
  ticker: string | null
  description: string | null
  fact_count: number
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  relation_type: RelationType
  evidence_text: string
  confidence: number
  event_time: string | null
  document_url: string | null
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  total_entities: number
  total_facts: number
}

export interface BottleneckReport {
  resource_name: string
  resource_type: EntityType
  constrained_count: number
  constrained_entities: Entity[]
  evidence_samples: string[]
  description: string
}

export interface DemandChain {
  concept: Entity
  enabled_products: Entity[]
  supplier_companies: Entity[]
  constrained_resources: Entity[]
}

export interface GraphStats {
  entities: Record<EntityType, number>
  facts: Record<RelationType, number>
  total_entities: number
  total_facts: number
  documents: { total: number; done: number }
}

export interface SourceDoc {
  id: string
  url: string
  document_type: string
  ticker: string | null
  company_name: string | null
  status: DocumentStatus
  chunk_count: number
  fact_count: number
  created_at: string
  ingested_at: string | null
}

export interface IngestRequest {
  url: string
  document_type: DocumentType
  ticker?: string
  company_name?: string
  filing_date?: string
  period_of_report?: string
  section?: string
  title?: string
}

export interface IngestTextRequest {
  text: string
  document_type: DocumentType
  ticker?: string
  company_name?: string
  period_of_report?: string
  section?: string
  title?: string
}

const BASE = '/api/v1/supply-chain'

export const supplyChainApi = {
  getGraph: async (params?: {
    entity_types?: string
    relation_types?: string
    ticker?: string
    min_confidence?: number
    since?: string
    limit?: number
  }): Promise<GraphData> => {
    const { data } = await apiClient.get(`${BASE}/graph`, { params })
    return data
  },

  getStats: async (): Promise<GraphStats> => {
    const { data } = await apiClient.get(`${BASE}/stats`)
    return data
  },

  getEntities: async (params?: {
    entity_type?: EntityType
    ticker?: string
    search?: string
    limit?: number
  }): Promise<Entity[]> => {
    const { data } = await apiClient.get(`${BASE}/entities`, { params })
    return data
  },

  createEntity: async (body: {
    entity_type: EntityType
    name: string
    aliases?: string[]
    description?: string
    ticker?: string
  }): Promise<Entity> => {
    const { data } = await apiClient.post(`${BASE}/entities`, body)
    return data
  },

  getEntityFacts: async (id: string, direction?: 'inbound' | 'outbound' | 'both'): Promise<Fact[]> => {
    const { data } = await apiClient.get(`${BASE}/entities/${id}/facts`, {
      params: { direction },
    })
    return data
  },

  getFacts: async (params?: {
    relation_type?: RelationType
    min_confidence?: number
    doc_id?: string
    limit?: number
  }): Promise<Fact[]> => {
    const { data } = await apiClient.get(`${BASE}/facts`, { params })
    return data
  },

  createFact: async (body: {
    source_entity_id: string
    target_entity_id: string
    relation_type: RelationType
    evidence_text: string
    confidence?: number
    event_time?: string
    document_url?: string
    document_section?: string
  }): Promise<Fact> => {
    const { data } = await apiClient.post(`${BASE}/facts`, body)
    return data
  },

  getBottlenecks: async (): Promise<BottleneckReport[]> => {
    const { data } = await apiClient.get(`${BASE}/analysis/bottlenecks`)
    return data
  },

  getDemandChain: async (concept: string): Promise<DemandChain> => {
    const { data } = await apiClient.get(`${BASE}/analysis/demand-chain/${encodeURIComponent(concept)}`)
    return data
  },

  getDocuments: async (params?: {
    ticker?: string
    document_type?: string
    status?: DocumentStatus
    limit?: number
  }): Promise<SourceDoc[]> => {
    const { data } = await apiClient.get(`${BASE}/documents`, { params })
    return data
  },

  ingestDocument: async (body: IngestRequest): Promise<{ doc_id: string; status: string; message: string }> => {
    const { data } = await apiClient.post(`${BASE}/ingest`, body)
    return data
  },

  ingestText: async (body: IngestTextRequest): Promise<{ doc_id: string; status: string; message: string }> => {
    const { data } = await apiClient.post(`${BASE}/ingest/text`, body)
    return data
  },

  ingestSec: async (params: {
    ticker: string
    form_type?: string
    section?: string
  }): Promise<{ status: string; message: string }> => {
    const { data } = await apiClient.post(`${BASE}/ingest/sec`, null, { params })
    return data
  },

  ingestEarningsCall: async (params: {
    ticker: string
    year: number
    quarter: number
  }): Promise<{ status: string; message: string }> => {
    const { data } = await apiClient.post(`${BASE}/ingest/earnings-call`, null, { params })
    return data
  },

  searchSecFilings: async (params: {
    ticker: string
    form_types?: string
    start_date?: string
    end_date?: string
    max_results?: number
  }): Promise<{ ticker: string; results: Array<{
    form: string
    filing_date: string
    period_of_report: string
    entity_name: string
    ticker: string
    index_url: string | null
  }>; count: number }> => {
    const { data } = await apiClient.get(`${BASE}/ingest/sec/search`, { params })
    return data
  },

  listEarningsCallAvailable: async (ticker: string): Promise<{
    ticker: string
    available: Array<{ year: number; quarter: number; date: string }>
    count: number
  }> => {
    const { data } = await apiClient.get(`${BASE}/ingest/earnings-call/list`, { params: { ticker } })
    return data
  },
}
