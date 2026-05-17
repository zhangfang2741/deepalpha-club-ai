"""因子 Skill 模型（平台精选 + 用户私有）。"""
from __future__ import annotations

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field, SQLModel

from app.db.base import UUIDModel


class FactorSkill(UUIDModel, table=True):
    """因子 Skill（平台精选 + 用户私有）。"""

    __tablename__ = "factor_skills"
    __table_args__ = (
        Index("ix_factor_skills_owner", "owner_id"),
        Index("ix_factor_skills_category", "category"),
    )

    owner_id: int | None = Field(default=None, index=True, nullable=True)
    title: str = Field(..., max_length=80, nullable=False)
    description: str = Field(..., max_length=200, nullable=False)
    category: str = Field(..., max_length=30, nullable=False)
    code: str = Field(..., nullable=False)
    default_symbol: str = Field(..., max_length=20, nullable=False)
    default_start_date: str = Field(..., max_length=10, nullable=False)
    default_end_date: str = Field(..., max_length=10, nullable=False)
    default_freq: str = Field(default="daily", max_length=10, nullable=False)
    snapshot_factor_jsonb: object = Field(sa_column=Column(JSON), default_factory=dict)
    narrative_jsonb: object = Field(sa_column=Column(JSON), default=None)
    is_public: bool = Field(default=False, nullable=False)
    pin_priority: int | None = Field(default=None, nullable=True)
