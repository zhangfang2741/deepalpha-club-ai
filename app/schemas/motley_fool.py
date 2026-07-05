"""Motley Fool earnings call transcript schemas."""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.base import BaseResponse


class TranscriptCandidate(BaseResponse):
    """A Motley Fool transcript search result."""

    title: str = Field(description="Transcript title")
    url: str = Field(description="Motley Fool article URL")
    published_at: Optional[datetime] = Field(default=None, description="Publish timestamp when available")


class TranscriptSegment(BaseResponse):
    """A transcript paragraph grouped by speaker when possible."""

    speaker: Optional[str] = Field(default=None, description="Speaker name when detected")
    text: str = Field(description="Transcript text")
    section: str = Field(description="prepared_remarks or questions_and_answers")


class EarningsCallTranscriptResponse(BaseResponse):
    """Motley Fool earnings call transcript response."""

    ticker: str = Field(description="Ticker symbol")
    title: str = Field(description="Transcript title")
    url: str = Field(description="Motley Fool source URL")
    source: str = Field(default="The Motley Fool", description="Transcript source")
    published_date: Optional[date] = Field(default=None, description="Published date parsed from URL or page metadata")
    prepared_remarks: str = Field(description="Prepared remarks transcript text")
    questions_and_answers: str = Field(description="Q&A transcript text")
    segments: List[TranscriptSegment] = Field(description="Detected transcript segments")
    candidates: List[TranscriptCandidate] = Field(description="Candidate transcript pages considered")


class EarningsCallTranscriptListResponse(BaseResponse):
    """Available Motley Fool transcript list for a ticker."""

    ticker: str = Field(description="Ticker symbol")
    source: str = Field(default="The Motley Fool", description="Transcript source")
    transcripts: List[TranscriptCandidate] = Field(description="Available earnings call transcripts")


class TranscriptSummary(BaseModel):
    """财报电话会议的结构化中文摘要。"""

    overview: str = Field(description="整体概述，一段话说明本次电话会议的核心信息")
    key_points: List[str] = Field(default_factory=list, description="核心要点列表")
    financial_highlights: List[str] = Field(
        default_factory=list, description="财务亮点：营收、利润、增长、利润率等关键数据"
    )
    guidance: str = Field(default="", description="业绩指引与前景展望；若未提及则留空")
    qa_highlights: List[str] = Field(default_factory=list, description="问答环节的关键问题与管理层回应")
    risks: List[str] = Field(default_factory=list, description="风险、挑战或不确定性")


class TranscriptSummaryRequest(BaseModel):
    """请求对逐字稿做中文总结。"""

    ticker: str = Field(description="Ticker symbol")
    title: str = Field(default="", description="Transcript title")
    url: str = Field(default="", description="Transcript source URL，用于结果缓存")
    prepared_remarks: str = Field(description="Prepared remarks transcript text")
    questions_and_answers: str = Field(description="Q&A transcript text")


class TranscriptSummaryResponse(BaseResponse):
    """逐字稿中文摘要响应。"""

    ticker: str = Field(description="Ticker symbol")
    title: str = Field(default="", description="Transcript title")
    url: str = Field(default="", description="Transcript source URL")
    summary: TranscriptSummary = Field(description="结构化中文摘要")


class TranscriptTranslationRequest(BaseModel):
    """请求把逐字稿翻译成中文。"""

    ticker: str = Field(description="Ticker symbol")
    url: str = Field(default="", description="Transcript source URL，用于结果缓存")
    prepared_remarks: str = Field(description="Prepared remarks transcript text")
    questions_and_answers: str = Field(description="Q&A transcript text")


class TranscriptTranslationResponse(BaseResponse):
    """逐字稿中文翻译响应。"""

    ticker: str = Field(description="Ticker symbol")
    url: str = Field(default="", description="Transcript source URL")
    prepared_remarks_zh: str = Field(description="管理层发言的中文翻译")
    questions_and_answers_zh: str = Field(description="问答环节的中文翻译")
