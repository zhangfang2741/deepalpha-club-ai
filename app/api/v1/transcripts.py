"""Earnings call transcript API endpoints."""

import json
from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import logger
from app.schemas.motley_fool import (
    EarningsCallTranscriptListResponse,
    EarningsCallTranscriptResponse,
    TranscriptSummaryRequest,
    TranscriptSummaryResponse,
    TranscriptTranslationRequest,
    TranscriptTranslationResponse,
)
from app.services.motley_fool import motley_fool_transcript_service
from app.services.transcript_ai import transcript_ai_service

router = APIRouter()
TRANSCRIPT_PARSE_ERRORS = {"q_and_a_section_not_found", "prepared_remarks_not_found"}


@router.get("/{ticker}", response_model=EarningsCallTranscriptListResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["transcripts"][0])
async def list_motley_fool_transcripts(
    request: Request,
    ticker: str,
    limit: Annotated[int, Query(ge=1, le=12, description="Maximum transcript pages to list")] = 8,
) -> EarningsCallTranscriptListResponse:
    """List recent Motley Fool earnings call transcripts for a ticker."""
    logger.info("motley_fool_transcript_list_endpoint_called", ticker=ticker, limit=limit)
    try:
        return await motley_fool_transcript_service.list_transcripts(ticker, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("motley_fool_transcript_list_endpoint_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=502, detail="Failed to fetch Motley Fool transcript list")


@router.get("/{ticker}/latest", response_model=EarningsCallTranscriptResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["transcripts"][0])
async def get_latest_motley_fool_transcript(
    request: Request,
    ticker: str,
    limit: Annotated[int, Query(ge=1, le=10, description="Maximum candidate transcript pages to try")] = 5,
) -> EarningsCallTranscriptResponse:
    """Fetch the latest Motley Fool earnings call transcript and Q&A for a ticker."""
    logger.info("motley_fool_transcript_endpoint_called", ticker=ticker, limit=limit)
    try:
        return await motley_fool_transcript_service.get_latest_transcript(ticker, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("motley_fool_transcript_endpoint_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=502, detail="Failed to fetch Motley Fool transcript")


@router.get("/{ticker}/detail", response_model=EarningsCallTranscriptResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["transcripts"][0])
async def get_motley_fool_transcript_detail(
    request: Request,
    ticker: str,
    url: Annotated[str, Query(description="Motley Fool transcript URL")],
) -> EarningsCallTranscriptResponse:
    """Fetch a specific Motley Fool earnings call transcript and Q&A."""
    logger.info("motley_fool_transcript_detail_endpoint_called", ticker=ticker, url=url)
    try:
        return await motley_fool_transcript_service.get_transcript_by_url(ticker, url)
    except ValueError as e:
        if str(e) in TRANSCRIPT_PARSE_ERRORS:
            raise HTTPException(status_code=502, detail="Motley Fool transcript page could not be parsed")
        raise HTTPException(status_code=422, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Motley Fool transcript page not found")
    except Exception as e:
        logger.exception("motley_fool_transcript_detail_endpoint_failed", ticker=ticker, url=url, error=str(e))
        raise HTTPException(status_code=502, detail="Failed to fetch Motley Fool transcript")


@router.post("/summarize", response_model=TranscriptSummaryResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["transcripts"][0])
async def summarize_transcript(
    request: Request,
    payload: TranscriptSummaryRequest,
) -> TranscriptSummaryResponse:
    """生成财报电话会议逐字稿的结构化中文摘要。"""
    logger.info("transcript_summarize_endpoint_called", ticker=payload.ticker, url=payload.url)
    if not payload.prepared_remarks.strip() and not payload.questions_and_answers.strip():
        raise HTTPException(status_code=422, detail="transcript content is empty")
    try:
        return await transcript_ai_service.summarize(
            ticker=payload.ticker,
            title=payload.title,
            url=payload.url,
            prepared_remarks=payload.prepared_remarks,
            questions_and_answers=payload.questions_and_answers,
        )
    except Exception as e:
        logger.exception("transcript_summarize_endpoint_failed", ticker=payload.ticker, error=str(e))
        raise HTTPException(status_code=502, detail="Failed to summarize transcript")


@router.post("/translate", response_model=TranscriptTranslationResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["transcripts"][0])
async def translate_transcript(
    request: Request,
    payload: TranscriptTranslationRequest,
) -> TranscriptTranslationResponse:
    """把财报电话会议逐字稿翻译成中文。"""
    logger.info("transcript_translate_endpoint_called", ticker=payload.ticker, url=payload.url)
    if not payload.prepared_remarks.strip() and not payload.questions_and_answers.strip():
        raise HTTPException(status_code=422, detail="transcript content is empty")
    try:
        return await transcript_ai_service.translate(
            ticker=payload.ticker,
            url=payload.url,
            prepared_remarks=payload.prepared_remarks,
            questions_and_answers=payload.questions_and_answers,
        )
    except Exception as e:
        logger.exception("transcript_translate_endpoint_failed", ticker=payload.ticker, error=str(e))
        raise HTTPException(status_code=502, detail="Failed to translate transcript")


@router.post("/translate/stream")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["transcripts"][0])
async def translate_transcript_stream(
    request: Request,
    payload: TranscriptTranslationRequest,
) -> StreamingResponse:
    """流式翻译逐字稿：按从前到后的顺序，逐段返回中文（SSE）。"""
    logger.info("transcript_translate_stream_endpoint_called", ticker=payload.ticker, url=payload.url)
    if not payload.prepared_remarks.strip() and not payload.questions_and_answers.strip():
        raise HTTPException(status_code=422, detail="transcript content is empty")

    async def event_generator():
        """逐段产出 SSE 事件。"""
        try:
            async for section, text in transcript_ai_service.translate_stream(
                ticker=payload.ticker,
                url=payload.url,
                prepared_remarks=payload.prepared_remarks,
                questions_and_answers=payload.questions_and_answers,
            ):
                yield f"data: {json.dumps({'section': section, 'text': text, 'done': False})}\n\n"
            yield f"data: {json.dumps({'section': None, 'text': '', 'done': True})}\n\n"
        except Exception as e:
            logger.exception("transcript_translate_stream_failed", ticker=payload.ticker, error=str(e))
            yield f"data: {json.dumps({'error': 'translation failed', 'done': True})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
