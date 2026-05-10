"""Analysis API endpoints for structural investment scoring."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.logging import logger
from app.core.langgraph.tools.analyze_stock import analyze_stock_async

router = APIRouter(tags=["analysis"])


class AnalysisRequest(BaseModel):
    """Request model for stock analysis."""
    ticker: str = Field(description="Stock ticker symbol (e.g., 'NVDA', 'AAPL')", min_length=1, max_length=10)
    include_industry: bool = Field(default=True, description="Include industry analysis")
    include_sentiment: bool = Field(default=True, description="Include news sentiment analysis")
    as_of_date: Optional[str] = Field(
        default=None, 
        description="Historical date for time travel (YYYY-MM-DD)"
    )


class LayerResult(BaseModel):
    """Result for a single analysis layer."""
    score: float = Field(ge=0, le=100, description="Layer score (0-100)")
    summary: str = Field(description="Layer summary")
    key_findings: List[str] = Field(description="Key findings")
    confidence: float = Field(ge=0, le=1, description="Confidence level")


class DataPointResult(BaseModel):
    """A traceable data point."""
    value: Any = Field(description="The data value")
    label: str = Field(description="Label/description")
    source: str = Field(description="Data source")
    url: Optional[str] = Field(default=None, description="Source URL")
    fetched_at: str = Field(description="Fetch timestamp")


class AnalysisResponse(BaseModel):
    """Response model for stock analysis."""
    ticker: str = Field(description="Stock ticker")
    company_name: str = Field(description="Company name")
    final_score: float = Field(ge=0, le=100, description="Final investment score (0-100)")
    recommendation: str = Field(description="Recommendation: BUY/HOLD/SELL")
    risk_reward_ratio: float = Field(description="Risk/reward ratio")
    position_recommendation: str = Field(description="Position size recommendation")
    layers: Dict[str, LayerResult] = Field(description="Layer-by-layer analysis")
    sources: List[DataPointResult] = Field(description="Source attribution")
    analysis_timestamp: str = Field(description="Analysis timestamp")
    analysis_duration_seconds: Optional[float] = Field(default=None, description="Analysis duration")


@router.post("/stock", response_model=AnalysisResponse)
async def analyze_stock_endpoint(request: AnalysisRequest) -> AnalysisResponse:
    """Analyze a stock using the six-layer investment framework.
    
    This endpoint performs comprehensive investment analysis combining data from:
    - SEC EDGAR (financial filings)
    - Financial Modeling Prep (valuation metrics)
    - News API (sentiment analysis)
    - Fear & Greed Index (market sentiment)
    
    All data is traceable with source attribution.
    
    Args:
        request: Analysis request with ticker and options
        
    Returns:
        Comprehensive analysis report with final score, recommendation,
        and layer-by-layer breakdown with source attribution.
        
    Raises:
        HTTPException: If analysis fails
    """
    logger.info("stock_analysis_request_received", ticker=request.ticker)
    
    start_time = datetime.utcnow()
    
    try:
        # Call the async analysis tool
        result = await analyze_stock_async(
            ticker=request.ticker.upper(),
            include_industry=request.include_industry,
            include_sentiment=request.include_sentiment,
            as_of_date=request.as_of_date,
        )
        
        # Calculate duration
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        # Check for errors in result
        if "error" in result:
            logger.error("stock_analysis_error", ticker=request.ticker, error=result["error"])
            raise HTTPException(status_code=500, detail=result["error"])
        
        # Convert to response model
        layers = {
            name: LayerResult(**layer_data)
            for name, layer_data in result.get("layers", {}).items()
        }
        
        sources = [
            DataPointResult(**source)
            for source in result.get("sources", [])
        ]
        
        logger.info(
            "stock_analysis_completed",
            ticker=request.ticker,
            score=result["final_score"],
            recommendation=result["recommendation"],
            duration_seconds=duration,
        )
        
        return AnalysisResponse(
            ticker=result["ticker"],
            company_name=result["company_name"],
            final_score=result["final_score"],
            recommendation=result["recommendation"],
            risk_reward_ratio=result["risk_reward_ratio"],
            position_recommendation=result["position_recommendation"],
            layers=layers,
            sources=sources,
            analysis_timestamp=result["analysis_timestamp"],
            analysis_duration_seconds=round(duration, 2),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("stock_analysis_failed", ticker=request.ticker, error=str(e))
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/stock/{ticker}")
async def get_stock_analysis(
    ticker: str,
    include_industry: bool = Query(default=True),
    include_sentiment: bool = Query(default=True),
    as_of_date: Optional[str] = Query(default=None),
) -> AnalysisResponse:
    """Get stock analysis via GET request.
    
    This is an alternative GET endpoint for fetching stock analysis.
    
    Args:
        ticker: Stock ticker symbol
        include_industry: Include industry analysis
        include_sentiment: Include sentiment analysis
        as_of_date: Historical date for time travel (YYYY-MM-DD)
        
    Returns:
        Comprehensive analysis report
    """
    request = AnalysisRequest(
        ticker=ticker,
        include_industry=include_industry,
        include_sentiment=include_sentiment,
        as_of_date=as_of_date,
    )
    return await analyze_stock_endpoint(request)


@router.get("/layers")
async def list_available_layers() -> Dict[str, Any]:
    """List all available analysis layers and their descriptions."""
    return {
        "layers": [
            {
                "name": "company",
                "display_name": "Company Quality",
                "description": "Quality of company management and operations",
                "weight": 0.20,
            },
            {
                "name": "financial",
                "display_name": "Financial Health",
                "description": "Revenue, profit, cash flow, and debt metrics",
                "weight": 0.25,
            },
            {
                "name": "industry",
                "display_name": "Industry Outlook",
                "description": "Industry growth and competitive dynamics",
                "weight": 0.15,
            },
            {
                "name": "expectation",
                "display_name": "Market Expectation",
                "description": "Market sentiment and expectations",
                "weight": 0.15,
            },
            {
                "name": "competition",
                "display_name": "Competition",
                "description": "Competitive position and moat",
                "weight": 0.10,
            },
            {
                "name": "trading",
                "display_name": "Trading & Valuation",
                "description": "Valuation and technical factors",
                "weight": 0.15,
            },
        ],
        "recommendations": {
            "BUY": "Score >= 70: Strong buy signal",
            "HOLD": "Score 50-70: Hold or accumulate on dips",
            "SELL": "Score < 50: Reduce or exit position",
        },
    }


@router.get("/health")
async def analysis_health_check() -> Dict[str, str]:
    """Health check for analysis service."""
    return {"status": "healthy", "service": "analysis"}