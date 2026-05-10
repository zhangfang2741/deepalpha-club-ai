"""Analysis database models."""

import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Float, Integer, String, Text, DateTime, Boolean, Index
from sqlmodel import Field, SQLModel

from app.db.base import UUIDModel


class AnalysisReportModel(UUIDModel, table=True):
    """Model for storing analysis reports."""
    
    __tablename__ = "analysis_reports"
    
    ticker: str = Field(sa_column=String(10), index=True, description="Stock ticker")
    company_name: str = Field(sa_column=String(255), description="Company name")
    final_score: float = Field(sa_column=Float, description="Final investment score (0-100)")
    recommendation: str = Field(sa_column=String(20), description="BUY/HOLD/SELL")
    risk_reward_ratio: float = Field(sa_column=Float, description="Risk/reward ratio")
    position_recommendation: str = Field(sa_column=String(50), description="Position size")
    
    # Layer scores stored as JSON
    layers_data: Dict[str, Any] = Field(
        sa_column=JSON, 
        description="Layer-by-layer analysis data"
    )
    
    # Source attribution stored as JSON
    sources_data: List[Dict[str, Any]] = Field(
        sa_column=JSON,
        description="Source attribution data"
    )
    
    # Metadata
    analysis_timestamp: datetime = Field(
        sa_column=DateTime, 
        index=True,
        description="When the analysis was performed"
    )
    analysis_duration_seconds: Optional[float] = Field(
        sa_column=Float, 
        nullable=True,
        description="Duration of analysis"
    )
    as_of_date: Optional[str] = Field(
        sa_column=String(10), 
        nullable=True,
        description="Historical date for time travel"
    )
    
    # User relationship
    user_id: Optional[uuid.UUID] = Field(
        sa_column=String(36), 
        nullable=True,
        index=True
    )
    
    # Caching
    is_cached: bool = Field(sa_column=Boolean, default=False, description="Is from cache")
    cache_ttl_seconds: int = Field(default=3600, description="Cache TTL in seconds")
    
    __table_args__ = (
        Index("ix_analysis_ticker_timestamp", "ticker", "analysis_timestamp"),
    )


class AnalysisDataPoint(UUIDModel, table=True):
    """Model for storing individual data points in analysis."""
    
    __tablename__ = "analysis_data_points"
    
    report_id: uuid.UUID = Field(
        index=True,
        description="Reference to analysis report"
    )
    
    # Data point details
    label: str = Field(sa_column=String(100), description="Label/description")
    value: Any = Field(sa_column=JSON, description="The data value")
    value_type: str = Field(sa_column=String(50), description="Type: number, string, date")
    
    # Source attribution
    source: str = Field(sa_column=String(100), description="Data source name")
    source_url: Optional[str] = Field(
        sa_column=Text, 
        nullable=True,
        description="Source URL for reference"
    )
    fetched_at: datetime = Field(
        sa_column=DateTime, 
        description="When the data was fetched"
    )
    
    # Layer assignment
    layer_name: str = Field(sa_column=String(50), index=True, description="Which layer this belongs to")
    
    __table_args__ = (
        Index("ix_data_points_report_layer", "report_id", "layer_name"),
    )