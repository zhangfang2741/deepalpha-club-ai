"""API v1 router configuration."""

from fastapi import APIRouter

from app.api.v1.analysis import router as analysis_router
from app.api.v1.analyst_upgrade import router as analyst_upgrade_router
from app.api.v1.auth import router as auth_router
from app.api.v1.chan import router as chan_router
from app.api.v1.chatbot import router as chatbot_router
from app.api.v1.etf import router as etf_router
from app.api.v1.fear_greed import router as fear_greed_router
from app.api.v1.ichimoku import router as ichimoku_router
from app.api.v1.industry_panic import router as industry_panic_router
from app.api.v1.institutional_signals import router as institutional_signals_router
from app.api.v1.research import router as research_router
from app.api.v1.sec_filings import router as sec_filings_router
from app.api.v1.settings import router as settings_router
from app.api.v1.skills import router as skills_router
from app.api.v1.supply_chain import router as supply_chain_router
from app.api.v1.supply_chain_map import router as supply_chain_map_router
from app.api.v1.transcripts import router as transcripts_router
from app.api.v1.valuation import router as valuation_router
from app.api.v1.wyckoff import router as wyckoff_router
from app.core.logging import logger

api_router = APIRouter()

api_router.include_router(analysis_router, prefix="/analysis", tags=["analysis"])
api_router.include_router(analyst_upgrade_router, prefix="/analyst-upgrades", tags=["analyst-upgrades"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(chan_router, prefix="/chan", tags=["chan"])
api_router.include_router(chatbot_router, prefix="/chatbot", tags=["chatbot"])
api_router.include_router(etf_router, prefix="/etf", tags=["etf"])
api_router.include_router(fear_greed_router, prefix="/fear-greed", tags=["fear-greed"])
api_router.include_router(ichimoku_router, prefix="/ichimoku", tags=["ichimoku"])
api_router.include_router(industry_panic_router, prefix="/industry-panic", tags=["industry-panic"])
api_router.include_router(institutional_signals_router, prefix="/institutional-signals", tags=["institutional-signals"])
api_router.include_router(research_router, prefix="/research", tags=["research"])
api_router.include_router(sec_filings_router, prefix="/sec", tags=["sec"])
api_router.include_router(settings_router, prefix="/settings", tags=["settings"])
api_router.include_router(skills_router, prefix="/skills", tags=["skills"])
api_router.include_router(supply_chain_router, prefix="/supply-chain", tags=["supply-chain"])
api_router.include_router(supply_chain_map_router, prefix="/supply-graph", tags=["supply-graph"])
api_router.include_router(transcripts_router, prefix="/transcripts", tags=["transcripts"])
api_router.include_router(valuation_router, prefix="/valuation", tags=["valuation"])
api_router.include_router(wyckoff_router, prefix="/wyckoff", tags=["wyckoff"])


@api_router.get("/health")
async def health_check():
    """Health check endpoint."""
    logger.info("health_check_called")
    return {"status": "healthy", "version": "1.0.0"}


@api_router.get("/hello")
async def hello():
    """Hello endpoint."""
    return {"deepalpha-club-ai": True}
