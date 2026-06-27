"""行业研究 API 端点，以 SSE 流式输出 7 步结构化研究报告."""

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.limiter import limiter
from app.core.logging import logger
from app.schemas.research import IndustryResearchRequest
from app.services.research import industry_research_service

router = APIRouter()


@router.post("/industry")
@limiter.limit("10 per minute")
async def research_industry(
    request: Request,
    body: IndustryResearchRequest,
) -> StreamingResponse:
    """启动行业研究，以 SSE 流式返回 7 个步骤结果."""
    logger.info("industry_research_started", industry=body.industry)

    async def event_generator():
        try:
            async for event_dict in industry_research_service.research_industry(body.industry):
                yield f"data: {json.dumps(event_dict, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception("industry_research_stream_failed", error=str(e))
            error_payload = {
                "event": "error",
                "step_index": None,
                "step_key": None,
                "message": str(e),
                "done": True,
            }
            yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
