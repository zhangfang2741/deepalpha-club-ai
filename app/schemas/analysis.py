"""Analysis schemas for structural investment analysis framework."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DataSource(str, Enum):
    """Data source identifiers."""
    SEC_EDGAR = "SEC EDGAR"
    FMP = "Financial Modeling Prep"
    CNN = "CNN Fear & Greed"
    NEWS_API = "News API"
    YAHOO_FINANCE = "Yahoo Finance"
    WHALE_WISDOM = "WhaleWisdom"
    WIKIPEDIA = "Wikipedia"
    CRUNCHBASE = "Crunchbase"


class LayerName(str, Enum):
    """Six-layer analysis framework layer names."""
    INDUSTRY = "industry"
    COMPANY = "company"
    FINANCIAL = "financial"
    COMPETITION = "competition"
    TRADING = "trading"
    EXPECTATION = "expectation"


class DataPoint(BaseModel):
    """A single data point with source attribution.
    
    Every analysis data point MUST carry source information for traceability.
    """
    value: Any = Field(description="The actual data value")
    label: str = Field(description="Human-readable label, e.g. 'Revenue 2024'")
    source: str = Field(description="Data source identifier, e.g. 'SEC EDGAR'")
    url: Optional[str] = Field(default=None, description="URL to original source for tracing")
    fetched_at: datetime = Field(default_factory=datetime.utcnow, description="When this data was fetched")


class LayerAnalysis(BaseModel):
    """Analysis result for a single layer."""
    layer_name: LayerName = Field(description="Name of the analysis layer")
    score: float = Field(ge=0, le=100, description="Layer score from 0-100")
    summary: str = Field(description="Brief summary of the layer analysis")
    key_findings: List[str] = Field(default_factory=list, description="Key findings in this layer")
    data_points: List[DataPoint] = Field(default_factory=list, description="Supporting data points")
    confidence: float = Field(ge=0, le=1, description="Confidence level of this analysis")


class AnalysisReport(BaseModel):
    """Complete six-layer analysis report."""
    ticker: str = Field(description="Stock ticker symbol")
    company_name: str = Field(description="Company name")
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    as_of_date: Optional[datetime] = Field(default=None, description="Date of analysis (for time travel)")
    
    # Six layers
    industry_analysis: Optional[LayerAnalysis] = Field(default=None, description="Industry layer analysis")
    company_analysis: Optional[LayerAnalysis] = Field(default=None, description="Company layer analysis")
    financial_analysis: Optional[LayerAnalysis] = Field(default=None, description="Financial layer analysis")
    competition_analysis: Optional[LayerAnalysis] = Field(default=None, description="Competition layer analysis")
    trading_analysis: Optional[LayerAnalysis] = Field(default=None, description="Trading layer analysis")
    expectation_analysis: Optional[LayerAnalysis] = Field(default=None, description="Expectation gap analysis")
    
    # Aggregated results
    final_score: float = Field(ge=0, le=100, description="Overall investment score 0-100")
    recommendation: str = Field(description="Investment recommendation: BUY, HOLD, or SELL")
    risk_reward_ratio: float = Field(description="Risk/reward ratio")
    position_recommendation: str = Field(description="Recommended position size")
    
    # Source tracking
    sources: List[DataPoint] = Field(default_factory=list, description="All data sources used")
    
    @classmethod
    def from_layers(cls, ticker: str, company_name: str, layers: Dict[str, LayerAnalysis]) -> "AnalysisReport":
        """Create report from layer analyses."""
        weights = {
            "industry": 0.20,
            "company": 0.20,
            "financial": 0.20,
            "competition": 0.15,
            "trading": 0.15,
            "expectation": 0.10,
        }
        
        all_sources: List[DataPoint] = []
        weighted_score = 0.0
        total_weight = 0.0
        
        layer_map = {}
        for name, analysis in layers.items():
            layer_map[name] = analysis
            if analysis and analysis.score > 0:
                weight = weights.get(name, 0.1)
                weighted_score += analysis.score * weight
                total_weight += weight
                all_sources.extend(analysis.data_points or [])
        
        final_score = weighted_score / total_weight if total_weight > 0 else 0.0
        
        # Determine recommendation based on score
        if final_score >= 70:
            recommendation = "BUY"
        elif final_score >= 50:
            recommendation = "HOLD"
        else:
            recommendation = "SELL"
        
        # Risk/reward (simplified)
        risk_reward = round(final_score / (100 - final_score + 1), 2)
        
        # Position size
        if final_score >= 80:
            position = "High Conviction (15-20%)"
        elif final_score >= 60:
            position = "Core Holding (8-12%)"
        elif final_score >= 40:
            position = "Small Position (3-5%)"
        else:
            position = "Avoid"
        
        return cls(
            ticker=ticker,
            company_name=company_name,
            industry_analysis=layer_map.get("industry"),
            company_analysis=layer_map.get("company"),
            financial_analysis=layer_map.get("financial"),
            competition_analysis=layer_map.get("competition"),
            trading_analysis=layer_map.get("trading"),
            expectation_analysis=layer_map.get("expectation"),
            final_score=round(final_score, 1),
            recommendation=recommendation,
            risk_reward_ratio=risk_reward,
            position_recommendation=position,
            sources=all_sources,
        )


class AnalysisRequest(BaseModel):
    """Request to start a new analysis."""
    ticker: str = Field(description="Stock ticker symbol (e.g., 'NVDA')")
    layers: List[LayerName] = Field(
        default_factory=lambda: list(LayerName),
        description="Layers to analyze"
    )
    as_of_date: Optional[str] = Field(
        default=None,
        description="Historical date for time travel analysis (YYYY-MM-DD)"
    )


class TaskStatus(str, Enum):
    """Analysis task status."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class LayerProgress(BaseModel):
    """Progress of a single layer."""
    layer: LayerName
    status: TaskStatus
    score: Optional[float] = None
    error: Optional[str] = None


class AnalysisTaskResponse(BaseModel):
    """Response when creating an analysis task."""
    task_id: str = Field(description="Unique task identifier")
    status: TaskStatus
    created_at: datetime
    ticker: str
    layers: List[LayerProgress]


class AnalysisTaskResult(BaseModel):
    """Full task result."""
    task_id: str
    status: TaskStatus
    ticker: str
    progress: List[LayerProgress]
    report: Optional[AnalysisReport] = None
    error: Optional[str] = None


class SSEProgressEvent(BaseModel):
    """Server-Sent Events progress update."""
    event: str = Field(default="progress", description="Event type")
    layer: str = Field(description="Layer name")
    status: TaskStatus
    score: Optional[float] = None
    message: Optional[str] = None


class SSECompleteEvent(BaseModel):
    """Server-Sent Events completion event."""
    event: str = Field(default="completed")
    report: AnalysisReport


class SSEErrorEvent(BaseModel):
    """Server-Sent Events error event."""
    event: str = Field(default="error")
    error: str
    layer: Optional[str] = None