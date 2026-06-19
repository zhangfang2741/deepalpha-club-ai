"""产业因果图谱 — 事实关系模型。"""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field

from app.db.base import UUIDModel


class RelationType(str, Enum):
    """四类产业链关系，覆盖"需求生成—能力支撑—产品实现—供给约束"完整链路。

    HAS_PRODUCT: Company → Product（公司定义/拥有产品线）
    SUPPLIED_BY: Product/Technology/Resource → Company（供应或制造来源）
    ENABLED_BY: Concept/Product → Technology/Resource（能力或资源支撑）
    CONSTRAINED_BY: Product/Concept/System → Resource/Technology（瓶颈限制）
    """

    HAS_PRODUCT = "HAS_PRODUCT"
    SUPPLIED_BY = "SUPPLIED_BY"
    ENABLED_BY = "ENABLED_BY"
    CONSTRAINED_BY = "CONSTRAINED_BY"


class GraphFact(UUIDModel, table=True):
    """产业因果关系事实，包含完整溯源元信息。

    每条 Fact 必须包含：原文证据、事实发生时间（event_time）、
    系统抽取时间（ingestion_time）及来源文档信息。
    """

    __tablename__ = "graph_facts"

    # 主体与客体
    source_entity_id: uuid.UUID = Field(
        foreign_key="graph_entities.id",
        index=True,
        nullable=False,
    )
    target_entity_id: uuid.UUID = Field(
        foreign_key="graph_entities.id",
        index=True,
        nullable=False,
    )
    relation_type: RelationType = Field(index=True)

    # 抽取证据
    evidence_text: str = Field()  # 原文句子
    confidence: float = Field(default=0.8)  # LLM 置信度 0-1

    # 时间元信息
    event_time: Optional[datetime] = Field(default=None, index=True)  # 事实发生时间
    ingestion_time: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    # 来源溯源
    source_doc_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key="graph_source_documents.id",
        index=True,
    )
    document_url: Optional[str] = Field(default=None)
    document_section: Optional[str] = Field(default=None)
    chunk_id: Optional[str] = Field(default=None)
