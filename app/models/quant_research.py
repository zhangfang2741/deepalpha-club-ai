"""量化研究四张表。存档均为「当时可见的数据」（point-in-time），不用事后修订值覆盖历史。"""

from __future__ import annotations

from datetime import date, datetime
from typing import ClassVar, Optional

from sqlalchemy import JSON, Column, Index, UniqueConstraint
from sqlmodel import Field

from app.db.base import UUIDModel


class QuantFundamentalSnapshot(UUIDModel, table=True):
    """每只股票最新的季度报表（利润表 16 季 / 现金流 8 季 / 最新资产负债表）。只在披露新财报后更新。"""

    __tablename__: ClassVar[str] = "quant_fundamental_snapshots"  # pyright: ignore[reportIncompatibleVariableOverride]
    __table_args__ = (UniqueConstraint("market", "symbol", name="uq_quant_fundamental"),)

    market: str = Field(max_length=8, nullable=False)
    symbol: str = Field(max_length=20, index=True, nullable=False)
    latest_quarter_date: Optional[str] = Field(default=None, max_length=10)
    filing_date: Optional[str] = Field(default=None, max_length=10)
    income_quarters: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    cash_quarters: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    balance: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    fetched_at: datetime = Field(nullable=False)


class QuantEstimateSnapshot(UUIDModel, table=True):
    """每日 × 股票 × 财年的一致预期快照（EPS 修正依赖；A 股 market=cn 同表）。只补不覆盖。"""

    __tablename__: ClassVar[str] = "quant_estimate_snapshots"  # pyright: ignore[reportIncompatibleVariableOverride]
    __table_args__ = (
        UniqueConstraint("market", "symbol", "snapshot_date", "fiscal_date", name="uq_quant_estimate"),
        Index("ix_quant_estimate_market_symbol", "market", "symbol"),
    )

    market: str = Field(max_length=8, nullable=False)
    symbol: str = Field(max_length=20, nullable=False)
    snapshot_date: date = Field(nullable=False)
    fiscal_date: str = Field(max_length=10, nullable=False)
    eps_avg: Optional[float] = None
    eps_low: Optional[float] = None
    eps_high: Optional[float] = None
    revenue_avg: Optional[float] = None
    ebitda_avg: Optional[float] = None
    ebit_avg: Optional[float] = None
    n_analysts: int = Field(default=0, nullable=False)


class QuantSectorDistribution(UUIDModel, table=True):
    """每日 × 板块 × 指标的升序数值（sector_key="_all"、metric_key="_overall" 存综合分分布）。"""

    __tablename__: ClassVar[str] = "quant_sector_distributions"  # pyright: ignore[reportIncompatibleVariableOverride]
    __table_args__ = (
        UniqueConstraint("market", "as_of", "sector_key", "metric_key", name="uq_quant_distribution"),
    )

    market: str = Field(max_length=8, nullable=False)
    as_of: date = Field(nullable=False, index=True)
    sector_key: str = Field(max_length=40, nullable=False)
    metric_key: str = Field(max_length=40, nullable=False)
    values: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))


class QuantResult(UUIDModel, table=True):
    """每日 × 股票的完整结果（中英两份响应）+ 各层等级（次日防抖用）。"""

    __tablename__: ClassVar[str] = "quant_results"  # pyright: ignore[reportIncompatibleVariableOverride]
    __table_args__ = (
        UniqueConstraint("market", "symbol", "as_of", name="uq_quant_result"),
        Index("ix_quant_result_market_symbol", "market", "symbol"),
    )

    market: str = Field(max_length=8, nullable=False)
    symbol: str = Field(max_length=20, nullable=False)
    as_of: date = Field(nullable=False, index=True)
    sector_key: str = Field(max_length=40, nullable=False)
    payload_zh: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    payload_en: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    grades: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


class QuantMoatAssessment(UUIDModel, table=True):
    """护城河评估：财务证据（10 年 ROIC vs 资金成本）+ 来源（大模型读 10-K）。

    一份 10-K（accession）× 方法版本只评一次；新年报出来另存一行，旧行保留（point-in-time）。
    """

    __tablename__: ClassVar[str] = "quant_moat_assessments"  # pyright: ignore[reportIncompatibleVariableOverride]
    __table_args__ = (
        UniqueConstraint("market", "symbol", "accession", "method_version", name="uq_quant_moat"),
        Index("ix_quant_moat_market_symbol", "market", "symbol"),
    )

    market: str = Field(max_length=8, nullable=False)
    symbol: str = Field(max_length=20, nullable=False)
    accession: str = Field(max_length=32, nullable=False)      # 10-K 编号
    filed_date: Optional[str] = Field(default=None, max_length=10)
    tenk_url: Optional[str] = Field(default=None, max_length=300)
    method_version: str = Field(max_length=8, nullable=False)
    rating: str = Field(max_length=8, nullable=False)           # wide | narrow | none
    trend: Optional[str] = Field(default=None, max_length=10)   # widening | stable | narrowing
    evidence: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    sources: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    threats: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))  # {"zh": ..., "en": ...}
    model_name: Optional[str] = Field(default=None, max_length=60)
    assessed_at: datetime = Field(nullable=False)
