"""产业因果图谱 — 原始来源文档模型。"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field

from app.db.base import UUIDModel


class DocumentType(str, Enum):
    """来源文档类型，按严格优先级排列。"""

    SEC_10K = "10-K"
    SEC_10Q = "10-Q"
    SEC_8K = "8-K"
    EARNINGS_CALL = "earnings_call"
    INVESTOR_RELATIONS = "investor_relations"


class DocumentStatus(str, Enum):
    """文档处理状态。"""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class SourceDocument(UUIDModel, table=True):
    """来源文档元信息，记录 SEC 文件、电话会议等原始数据来源。"""

    __tablename__ = "graph_source_documents"

    url: str = Field(index=True)
    document_type: DocumentType
    ticker: Optional[str] = Field(default=None, index=True)
    company_name: Optional[str] = Field(default=None)
    filing_date: Optional[datetime] = Field(default=None)
    period_of_report: Optional[datetime] = Field(default=None)
    section: Optional[str] = Field(default=None)
    title: Optional[str] = Field(default=None)

    # 处理进度
    chunk_count: int = Field(default=0)
    processed_chunks: int = Field(default=0)  # 已处理切片数，用于进度展示
    fact_count: int = Field(default=0)
    status: DocumentStatus = Field(default=DocumentStatus.PENDING)
    error_message: Optional[str] = Field(default=None)

    # 缓存去重键（deterministic）：命中已完成文档则跳过重复抓取/抽取
    cache_key: Optional[str] = Field(default=None, index=True)

    # 摄取时间
    ingested_at: Optional[datetime] = Field(default=None)
