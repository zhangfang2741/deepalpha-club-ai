"""产业供应链图谱 API 请求/响应 Schema。"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.graph_entity import EntityType
from app.models.graph_fact import RelationType
from app.models.graph_source import DocumentType


# ──────────────────────────────────────────────
# 摄取（Ingest）
# ──────────────────────────────────────────────


class IngestDocumentRequest(BaseModel):
    """手动触发文档摄取请求。"""

    url: str = Field(description="文档 URL，SEC EDGAR 直链或电话会议文字记录")
    document_type: DocumentType
    ticker: Optional[str] = Field(default=None, description="相关股票代码（如 NVDA）")
    company_name: Optional[str] = Field(default=None)
    filing_date: Optional[datetime] = Field(default=None)
    period_of_report: Optional[datetime] = Field(default=None)
    section: Optional[str] = Field(default=None, description="文档章节（如 Risk Factors）")
    title: Optional[str] = Field(default=None)


class IngestDocumentResponse(BaseModel):
    """文档摄取响应。"""

    doc_id: uuid.UUID
    status: str
    message: str


class IngestTextRequest(BaseModel):
    """直接摄取原始文本请求。"""

    text: str = Field(description="原始文本内容（电话会议记录、IR 材料等）", min_length=100)
    document_type: DocumentType
    ticker: Optional[str] = Field(default=None, description="相关股票代码（如 NVDA）")
    company_name: Optional[str] = Field(default=None)
    period_of_report: Optional[datetime] = Field(default=None, description="报告期 YYYY-MM-DD")
    section: Optional[str] = Field(default=None)
    title: Optional[str] = Field(default=None)


# ──────────────────────────────────────────────
# 实体（Entity）
# ──────────────────────────────────────────────


class EntityOut(BaseModel):
    """实体节点输出 Schema。"""

    id: uuid.UUID
    entity_type: EntityType
    name: str
    aliases: list[str]
    description: Optional[str]
    ticker: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class EntityCreate(BaseModel):
    """手动创建实体请求。"""

    entity_type: EntityType
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    ticker: Optional[str] = None


# ──────────────────────────────────────────────
# 事实（Fact）
# ──────────────────────────────────────────────


class FactOut(BaseModel):
    """事实关系输出 Schema。"""

    id: uuid.UUID
    source_entity_id: uuid.UUID
    target_entity_id: uuid.UUID
    source_entity_name: Optional[str] = None  # 通过 join 填充
    target_entity_name: Optional[str] = None
    source_entity_type: Optional[EntityType] = None
    target_entity_type: Optional[EntityType] = None
    relation_type: RelationType
    evidence_text: str
    confidence: float
    event_time: Optional[datetime]
    ingestion_time: datetime
    document_url: Optional[str]
    document_section: Optional[str]
    chunk_id: Optional[str]

    model_config = {"from_attributes": True}


class FactCreate(BaseModel):
    """手动创建事实请求。"""

    source_entity_id: uuid.UUID
    target_entity_id: uuid.UUID
    relation_type: RelationType
    evidence_text: str
    confidence: float = 0.8
    event_time: Optional[datetime] = None
    document_url: Optional[str] = None
    document_section: Optional[str] = None


# ──────────────────────────────────────────────
# 图谱查询
# ──────────────────────────────────────────────


class GraphNode(BaseModel):
    """前端图谱节点数据。"""

    id: str
    name: str
    entity_type: EntityType
    ticker: Optional[str]
    description: Optional[str]
    fact_count: int = 0


class GraphEdge(BaseModel):
    """前端图谱边数据。"""

    id: str
    source: str
    target: str
    relation_type: RelationType
    evidence_text: str
    confidence: float
    event_time: Optional[datetime]
    document_url: Optional[str]


class GraphData(BaseModel):
    """图谱可视化数据（节点 + 边）。"""

    nodes: list[GraphNode]
    edges: list[GraphEdge]
    total_entities: int
    total_facts: int


class GraphQueryParams(BaseModel):
    """图谱查询参数。"""

    entity_types: Optional[list[EntityType]] = None
    relation_types: Optional[list[RelationType]] = None
    ticker: Optional[str] = None
    min_confidence: float = 0.0
    limit: int = Field(default=200, ge=1, le=1000)


class BottleneckReport(BaseModel):
    """产业瓶颈分析报告。"""

    resource_name: str
    resource_type: EntityType
    constrained_count: int  # 受约束的实体数量
    constrained_entities: list[EntityOut]
    evidence_samples: list[str]


class DemandChain(BaseModel):
    """需求传导链路。"""

    concept: EntityOut
    enabled_products: list[EntityOut]
    supplier_companies: list[EntityOut]
    constrained_resources: list[EntityOut]
