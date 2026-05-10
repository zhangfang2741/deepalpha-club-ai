"""This file contains the schemas for the application."""

from app.schemas.analysis import (
    AnalysisRequest,
    AnalysisReport,
    AnalysisTaskResponse,
    AnalysisTaskResult,
    DataPoint,
    DataSource,
    LayerAnalysis,
    LayerName,
    LayerProgress,
    SSECompleteEvent,
    SSEErrorEvent,
    SSEProgressEvent,
    TaskStatus,
)
from app.schemas.auth import Token
from app.schemas.base import BaseResponse
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    Message,
    StreamResponse,
)
from app.schemas.graph import GraphState

__all__ = [
    # Analysis schemas
    "AnalysisRequest",
    "AnalysisReport",
    "AnalysisTaskResponse",
    "AnalysisTaskResult",
    "DataPoint",
    "DataSource",
    "LayerAnalysis",
    "LayerName",
    "LayerProgress",
    "SSECompleteEvent",
    "SSEErrorEvent",
    "SSEProgressEvent",
    "TaskStatus",
    # Auth schemas
    "Token",
    # Base schemas
    "BaseResponse",
    # Chat schemas
    "ChatRequest",
    "ChatResponse",
    "Message",
    "StreamResponse",
    # Graph schemas
    "GraphState",
]