"""API v1 router configuration."""

from fastapi import APIRouter

from app.api.v1.analysis import router as analysis_router
from app.api.v1.auth import router as auth_router
from app.api.v1.chatbot import router as chatbot_router
from app.api.v1.etf import router as etf_router
from app.api.v1.fear_greed import router as fear_greed_router
from app.api.v1.skills import router as skills_router
from app.api.v1.valuation import router as valuation_router
from app.core.logging import logger

api_router = APIRouter()

api_router.include_router(analysis_router, prefix="/analysis", tags=["analysis"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(chatbot_router, prefix="/chatbot", tags=["chatbot"])
api_router.include_router(etf_router, prefix="/etf", tags=["etf"])
api_router.include_router(fear_greed_router, prefix="/fear-greed", tags=["fear-greed"])
api_router.include_router(skills_router, prefix="/skills", tags=["skills"])
api_router.include_router(valuation_router, prefix="/valuation", tags=["valuation"])


@api_router.get("/health")
async def health_check():
    """Health check endpoint."""
    logger.info("health_check_called")
    return {"status": "healthy", "version": "1.0.0"}


@api_router.get("/hello")
async def hello():
    """Hello endpoint."""
    return {"deepalpha-club-ai": True}
