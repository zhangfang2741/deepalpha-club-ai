"""Motley Fool earnings call transcript schemas."""

from datetime import date, datetime
from typing import List, Optional

from pydantic import Field

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
