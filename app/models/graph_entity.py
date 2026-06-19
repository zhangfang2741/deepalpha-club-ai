"""产业因果图谱 — 实体模型。"""

from enum import Enum
from typing import Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field

from app.db.base import UUIDModel


class EntityType(str, Enum):
    """产业图谱实体类型。"""

    COMPANY = "Company"
    PRODUCT = "Product"
    TECHNOLOGY = "Technology"
    CONCEPT = "Concept"
    RESOURCE = "Resource"


class GraphEntity(UUIDModel, table=True):
    """产业图谱实体节点。

    五类实体覆盖 AI 产业链全貌：
    Company（公司）、Product（产品）、Technology（技术）、
    Concept（需求/市场概念）、Resource（资源与约束）。
    """

    __tablename__ = "graph_entities"

    entity_type: EntityType = Field(index=True)
    name: str = Field(index=True)  # 规范化主名称
    aliases: list = Field(default_factory=list, sa_column=Column(JSON))  # 别名列表
    description: Optional[str] = Field(default=None)
    ticker: Optional[str] = Field(default=None, index=True)  # 股票代码，仅 Company 有效

    # 来源文档 ID 列表（JSON 数组）
    source_doc_ids: list = Field(default_factory=list, sa_column=Column(JSON))

    class Config:  # noqa: D106
        arbitrary_types_allowed = True
