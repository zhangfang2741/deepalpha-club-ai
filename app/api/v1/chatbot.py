"""Chatbot API endpoints for handling chat interactions.

This module provides endpoints for chat interactions, including regular chat,
streaming chat, message history management, and chat history clearing.
"""

import json

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from fastapi.responses import StreamingResponse

from app.api.v1.auth import get_current_session
from app.core.config import settings
from app.core.langgraph.graph import LangGraphAgent
from app.core.limiter import limiter
from app.core.logging import logger
from app.core.metrics import llm_stream_duration_seconds
from app.models.session import Session
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    LangGraphChatRequest,
    StreamResponse,
)
from app.schemas.chat import Message as ChatMessage
from app.services.session_naming import maybe_name_session


def _extract_text(content) -> str:
    """从字符串或 LangChain 内容块数组中提取纯文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text") or block.get("content")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return ""


def _to_chat_messages(lg_messages) -> list[ChatMessage]:
    """把 useLangGraphRuntime 传入的消息转换为内部 Message（仅保留用户消息作为本轮输入）。"""
    result: list[ChatMessage] = []
    for m in lg_messages:
        role = m.role or ("user" if m.type in (None, "human") else m.type)
        if role in ("human", "user"):
            role = "user"
        elif role in ("ai", "assistant"):
            role = "assistant"
        else:
            continue
        text = _extract_text(m.content)
        if text.strip():
            result.append(ChatMessage(role=role, content=text))
    return result

router = APIRouter()
agent = LangGraphAgent()


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chat"][0])
async def chat(
    request: Request,
    chat_request: ChatRequest,
    session: Session = Depends(get_current_session),
):
    """Process a chat request using LangGraph.

    Args:
        request: The FastAPI request object for rate limiting.
        chat_request: The chat request containing messages.
        session: The current session from the auth token.

    Returns:
        ChatResponse: The processed chat response.

    Raises:
        HTTPException: If there's an error processing the request.
    """
    try:
        logger.info(
            "chat_request_received",
            session_id=session.id,
            message_count=len(chat_request.messages),
        )

        if settings.SESSION_NAMING_ENABLED:
            maybe_name_session(session.id, session.name, chat_request.messages)

        result = await agent.get_response(
            chat_request.messages, session.id, user_id=str(session.user_id), username=session.username
        )

        logger.info("chat_request_processed", session_id=session.id)

        return ChatResponse(messages=result)
    except Exception as e:
        logger.exception("chat_request_failed", session_id=session.id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chat_stream"][0])
async def chat_stream(
    request: Request,
    chat_request: ChatRequest,
    session: Session = Depends(get_current_session),
):
    """Process a chat request using LangGraph with streaming response.

    Args:
        request: The FastAPI request object for rate limiting.
        chat_request: The chat request containing messages.
        session: The current session from the auth token.

    Returns:
        StreamingResponse: A streaming response of the chat completion.

    Raises:
        HTTPException: If there's an error processing the request.
    """
    try:
        logger.info(
            "stream_chat_request_received",
            session_id=session.id,
            message_count=len(chat_request.messages),
        )

        if settings.SESSION_NAMING_ENABLED:
            maybe_name_session(session.id, session.name, chat_request.messages)

        async def event_generator():
            """Generate streaming events.

            Yields:
                str: Server-sent events in JSON format.

            Raises:
                Exception: If there's an error during streaming.
            """
            try:
                with llm_stream_duration_seconds.labels(model=settings.DEFAULT_LLM_MODEL).time():
                    async for chunk in agent.get_stream_response(
                        chat_request.messages, session.id, user_id=str(session.user_id), username=session.username
                    ):
                        response = StreamResponse(content=chunk, done=False)
                        yield f"data: {json.dumps(response.model_dump(mode='json'))}\n\n"

                # Send final message indicating completion
                final_response = StreamResponse(content="", done=True)
                yield f"data: {json.dumps(final_response.model_dump(mode='json'))}\n\n"

            except Exception as e:
                logger.exception(
                    "stream_chat_request_failed",
                    session_id=session.id,
                    error=str(e),
                )
                error_response = StreamResponse(content=str(e), done=True)
                yield f"data: {json.dumps(error_response.model_dump(mode='json'))}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as e:
        logger.exception(
            "stream_chat_request_failed",
            session_id=session.id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/langgraph/stream")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chat_stream"][0])
async def langgraph_stream(
    request: Request,
    chat_request: LangGraphChatRequest,
    session: Session = Depends(get_current_session),
):
    """Deep Agent 结构化事件流，供前端 assistant-ui useLangGraphRuntime 消费。

    以 SSE 逐条产出 ``{"event": ..., "data": ...}``，前端据此渲染流式文本、工具调用卡片
    （write_todos 规划 / task 子智能体 / 文件系统 / 投研工具）以及中断。

    Args:
        request: FastAPI 请求对象（用于限流）。
        chat_request: LangGraph 风格的聊天请求（新消息 + 可选恢复指令）。
        session: 当前会话（来自鉴权 token）。

    Returns:
        StreamingResponse: text/event-stream 事件流。
    """
    try:
        messages = _to_chat_messages(chat_request.messages)
        resume_value = chat_request.command.resume if chat_request.command else None

        logger.info(
            "langgraph_stream_request_received",
            session_id=session.id,
            message_count=len(messages),
            has_resume=resume_value is not None,
        )

        if not messages and resume_value is None:
            raise HTTPException(status_code=400, detail="no user message provided")

        if settings.SESSION_NAMING_ENABLED and messages:
            maybe_name_session(session.id, session.name, messages)

        async def event_generator():
            with llm_stream_duration_seconds.labels(model=settings.DEFAULT_LLM_MODEL).time():
                async for sse_chunk in agent.get_langgraph_stream(
                    messages,
                    session.id,
                    user_id=str(session.user_id),
                    username=session.username,
                    resume_value=resume_value,
                ):
                    yield sse_chunk

        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("langgraph_stream_request_failed", session_id=session.id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/langgraph/history")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["messages"][0])
async def langgraph_history(
    request: Request,
    session: Session = Depends(get_current_session),
):
    """返回 LangChain 风格的完整历史消息（含工具调用），供 useLangGraphRuntime 的 load 恢复。

    Args:
        request: FastAPI 请求对象（用于限流）。
        session: 当前会话（来自鉴权 token）。

    Returns:
        dict: ``{"messages": [...]}``，每条为序列化后的 LangChain 消息。
    """
    try:
        messages = await agent.get_langgraph_history(session.id)
        return {"messages": messages}
    except Exception as e:
        logger.exception("langgraph_history_failed", session_id=session.id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/messages", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["messages"][0])
async def get_session_messages(
    request: Request,
    session: Session = Depends(get_current_session),
):
    """Get all messages for a session.

    Args:
        request: The FastAPI request object for rate limiting.
        session: The current session from the auth token.

    Returns:
        ChatResponse: All messages in the session.

    Raises:
        HTTPException: If there's an error retrieving the messages.
    """
    try:
        messages = await agent.get_chat_history(session.id)
        return ChatResponse(messages=messages)
    except Exception as e:
        logger.exception("get_messages_failed", session_id=session.id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/messages")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["messages"][0])
async def clear_chat_history(
    request: Request,
    session: Session = Depends(get_current_session),
):
    """Clear all messages for a session.

    Args:
        request: The FastAPI request object for rate limiting.
        session: The current session from the auth token.

    Returns:
        dict: A message indicating the chat history was cleared.
    """
    try:
        await agent.clear_chat_history(session.id)
        return {"message": "Chat history cleared successfully"}
    except Exception as e:
        logger.exception("clear_chat_history_failed", session_id=session.id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
