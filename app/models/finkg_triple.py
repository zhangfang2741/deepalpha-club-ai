"""FinReflectKG 三元组模型 — 论文 5 元组格式存储。

与产业供应链图谱（graph_entities/graph_facts）相互独立：
本表按论文的开放数据集形态直接存 5 元组
(head, head_type, relation, tail, tail_type) + 原文证据与溯源信息，
类型取值由 app.services.graph.finreflect.ontology 本体约束（抽取期校验），
列本身为字符串以便本体补全时无需迁移。
"""

import uuid
from typing import Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field

from app.db.base import UUIDModel


class FinKGTriple(UUIDModel, table=True):
    """FinReflectKG 知识三元组（论文 5 元组 + 证据 + 溯源 + 合规标注）。"""

    __tablename__ = "finkg_triples"

    # 论文 5 元组
    head: str = Field(index=True, max_length=300)
    head_type: str = Field(index=True, max_length=50)
    relation: str = Field(index=True, max_length=50)
    tail: str = Field(index=True, max_length=300)
    tail_type: str = Field(index=True, max_length=50)

    # 原文证据（论文要求每条三元组可溯源到 chunk 内原句）
    evidence: str = Field(sa_column=Column(Text, nullable=False))

    # CheckRules 合规标注（规则化策略审计结果）
    compliant: bool = Field(default=True, index=True)
    violations: list = Field(default_factory=list, sa_column=Column(JSON))

    # 抽取元信息
    extraction_mode: str = Field(default="reflection", max_length=20)  # single_pass | multi_pass | reflection
    chunk_id: Optional[str] = Field(default=None, max_length=200)

    # 来源溯源
    source_doc_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key="graph_source_documents.id",
        index=True,
    )
    document_url: Optional[str] = Field(default=None, max_length=1000)
    ticker: Optional[str] = Field(default=None, index=True, max_length=20)
