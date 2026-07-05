"""The Motley Fool earnings call transcript fetcher."""

from __future__ import annotations

import asyncio
import html
import re
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Iterable, List, Optional, override
from urllib.parse import urljoin, urlparse

import httpx
from pydantic import TypeAdapter

from app.core.config import settings
from app.core.logging import logger
from app.schemas.motley_fool import (
    EarningsCallTranscriptListResponse,
    EarningsCallTranscriptResponse,
    TranscriptCandidate,
    TranscriptSegment,
)

FOOL_BASE_URL = "https://www.fool.com"
FOOL_USER_AGENT = "DeepAlpha/1.0 (investment research; Motley Fool transcript fetcher)"
QUOTE_EXCHANGES = ("nasdaq", "nyse", "amex")
TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
TRANSCRIPT_PATH_PATTERN = re.compile(r"/earnings/call-transcripts/[^\"\\\s<>]+", re.IGNORECASE)
PRESENTATION_URL_PATTERN = re.compile(
    r"https://www\.fool\.com/earnings/call-transcripts/[^\"\\\s<>]+",
    re.IGNORECASE,
)
QA_HEADING_PATTERN = re.compile(
    r"^questions?(?:\s+|[-&])?(?:and|&)?(?:\s+|-)?answers?(?:\s*session)?$",
    re.IGNORECASE,
)
PREPARED_HEADING_PATTERN = re.compile(r"^prepared\s+remarks?:?$", re.IGNORECASE)
STOP_HEADING_PATTERN = re.compile(
    r"^(call participants|stocks mentioned|related articles|motley fool returns|operator instructions)$",
    re.IGNORECASE,
)
FULL_TRANSCRIPT_HEADING_PATTERN = re.compile(r"^full\s+conference\s+call\s+transcript$", re.IGNORECASE)
QA_START_PATTERN = re.compile(
    r"(first question|next question|investor questions|analyst questions|head over to .*questions|"
    r"open (?:the )?call for questions|poll for questions|"
    r"begin (?:the )?question|question-and-answer|no further questions)",
    re.IGNORECASE,
)
SPEAKER_PREFIX_PATTERN = re.compile(r"^([A-Z][A-Za-z .'-]{1,70}(?:\s+--\s+[^:]{1,80})?):\s*(.+)$")


class _TextBlockParser(HTMLParser):
    """Collect readable text from common article tags."""

    block_tags = {"h1", "h2", "h3", "h4", "p", "li"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._active_tag: Optional[str] = None
        self._buffer: List[str] = []
        self.blocks: List[str] = []

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag in self.block_tags:
            self._flush()
            self._active_tag = tag

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag == self._active_tag:
            self._flush()
            self._active_tag = None

    @override
    def handle_data(self, data: str) -> None:
        if self._active_tag:
            self._buffer.append(data)

    def _flush(self) -> None:
        text = _clean_text(" ".join(self._buffer))
        self._buffer = []
        if text and text not in self.blocks:
            self.blocks.append(text)


def _clean_text(value: str) -> str:
    """Normalize whitespace and HTML entities."""
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _normalize_ticker(ticker: str) -> str:
    """Normalize and validate a US ticker symbol."""
    normalized = ticker.strip().upper().replace("/", ".")
    if not TICKER_PATTERN.fullmatch(normalized):
        raise ValueError("ticker must be 1-10 chars and contain only letters, numbers, dots, or dashes")
    return normalized


def _headers() -> dict[str, str]:
    """Build HTTP headers for Motley Fool requests."""
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "User-Agent": FOOL_USER_AGENT,
    }


def _http_proxy() -> Optional[str]:
    """Return configured outbound proxy if present."""
    return settings.HTTP_PROXY or settings.HTTPS_PROXY or None


async def _fetch_text(client: httpx.AsyncClient, url: str) -> str:
    """Fetch a page and return text content."""
    response = await client.get(url, headers=_headers(), follow_redirects=True)
    response.raise_for_status()
    return response.text


def _extract_title(page_text: str, fallback: str) -> str:
    """Extract a human readable page title."""
    for pattern in (
        r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']',
        r"<title>(.*?)</title>",
        r'"headline"\s*:\s*"([^"]+)"',
    ):
        match = re.search(pattern, page_text, re.IGNORECASE | re.DOTALL)
        if match:
            return _clean_text(match.group(1).replace("\\u0026", "&"))
    return fallback


def _extract_published_date(url: str, page_text: str) -> Optional[date]:
    """Extract publish date from metadata or Motley Fool URL path."""
    meta_match = re.search(
        r'<meta\s+property=["\']article:published_time["\']\s+content=["\']([^"\']+)["\']',
        page_text,
        re.IGNORECASE,
    )
    if meta_match:
        try:
            return datetime.fromisoformat(meta_match.group(1).replace("Z", "+00:00")).date()
        except ValueError:
            logger.warning("motley_fool_publish_date_parse_failed", value=meta_match.group(1))

    url_match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
    if not url_match:
        return None
    try:
        year, month, day = (int(part) for part in url_match.groups())
        return date(year, month, day)
    except ValueError:
        return None


def _extract_quote_candidates(page_text: str, ticker: str) -> list[TranscriptCandidate]:
    """Extract transcript candidates embedded in Fool quote HTML."""
    candidates: list[TranscriptCandidate] = []
    seen: set[str] = set()
    decoded = page_text.replace("\\/", "/").replace("\\u0026", "&")

    urls = [urljoin(FOOL_BASE_URL, match.group(0)) for match in TRANSCRIPT_PATH_PATTERN.finditer(decoded)]
    urls.extend(match.group(0) for match in PRESENTATION_URL_PATTERN.finditer(decoded))

    for url in urls:
        normalized_url = url.rstrip("/") + "/"
        lower_url = normalized_url.lower()
        if normalized_url in seen or ticker.lower() not in lower_url:
            continue
        seen.add(normalized_url)
        title = _title_from_url(normalized_url)
        candidates.append(
            TranscriptCandidate(
                title=title,
                url=normalized_url,
                published_at=_candidate_published_at(normalized_url),
            )
        )

    return candidates


def _title_from_url(url: str) -> str:
    """Build a readable title from a Motley Fool URL slug."""
    slug = url.rstrip("/").split("/")[-1]
    return slug.replace("-", " ").title()


def _candidate_published_at(url: str) -> Optional[datetime]:
    """Extract a candidate publish timestamp from a Motley Fool URL."""
    url_match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
    if not url_match:
        return None
    try:
        year, month, day = (int(part) for part in url_match.groups())
        return datetime(year, month, day)
    except ValueError:
        return None


def _validate_transcript_url(url: str, ticker: str) -> str:
    """Validate a Motley Fool transcript URL before fetching detail."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("url must be an http(s) Motley Fool transcript URL")
    if parsed.netloc not in {"www.fool.com", "fool.com"}:
        raise ValueError("url must point to fool.com")
    if not parsed.path.startswith("/earnings/call-transcripts/"):
        raise ValueError("url must point to a Motley Fool earnings call transcript")
    if ticker.lower() not in parsed.path.lower():
        raise ValueError("url does not appear to match the requested ticker")
    return f"https://www.fool.com{parsed.path.rstrip('/')}/"


def _search_duckduckgo_sync(ticker: str, limit: int) -> list[TranscriptCandidate]:
    """Search the web for Motley Fool transcript pages."""
    try:
        from ddgs import DDGS
    except ImportError:
        logger.warning("ddgs_not_available")
        return []

    query = f"site:fool.com/earnings/call-transcripts/ {ticker} earnings call transcript Motley Fool"
    candidates: list[TranscriptCandidate] = []
    seen: set[str] = set()

    try:
        with DDGS(proxy=_http_proxy()) as ddgs:
            for item in ddgs.text(query, max_results=max(limit * 2, 8)):
                href = str(item.get("href") or item.get("url") or "")
                title = _clean_text(str(item.get("title") or _title_from_url(href)))
                if "fool.com/earnings/call-transcripts/" not in href:
                    continue
                if ticker.lower() not in href.lower() and ticker.lower() not in title.lower():
                    continue
                normalized_url = href.split("?")[0].rstrip("/") + "/"
                if normalized_url in seen:
                    continue
                seen.add(normalized_url)
                candidates.append(
                    TranscriptCandidate(
                        title=title,
                        url=normalized_url,
                        published_at=_candidate_published_at(normalized_url),
                    )
                )
                if len(candidates) >= limit:
                    break
    except Exception as e:
        logger.exception("motley_fool_search_failed", ticker=ticker, error=str(e))

    return candidates


async def _search_duckduckgo(ticker: str, limit: int) -> list[TranscriptCandidate]:
    """Async wrapper around DuckDuckGo search."""
    return await asyncio.to_thread(_search_duckduckgo_sync, ticker, limit)


async def _filter_reachable_candidates(
    client: httpx.AsyncClient,
    candidates: list[TranscriptCandidate],
    limit: int,
) -> list[TranscriptCandidate]:
    """Keep candidate transcript pages that still return successful responses."""
    reachable: list[TranscriptCandidate] = []
    for candidate in candidates:
        try:
            response = await client.get(candidate.url, headers=_headers(), follow_redirects=True)
            response.raise_for_status()
        except Exception as e:
            logger.warning("motley_fool_candidate_unreachable", url=candidate.url, error=str(e))
            continue
        reachable.append(candidate)
        if len(reachable) >= limit:
            break
    return reachable


def _dedupe_candidates(candidates: Iterable[TranscriptCandidate], limit: int) -> list[TranscriptCandidate]:
    """Deduplicate candidates by URL."""
    unique: list[TranscriptCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized_url = candidate.url.split("?")[0].rstrip("/") + "/"
        if normalized_url in seen:
            continue
        seen.add(normalized_url)
        unique.append(candidate.model_copy(update={"url": normalized_url}))
        if len(unique) >= limit:
            break
    return unique


def _extract_text_blocks(page_text: str) -> list[str]:
    """Extract readable article blocks from HTML and Next.js payloads."""
    parser = _TextBlockParser()
    parser.feed(page_text)
    blocks = parser.blocks
    if blocks:
        return blocks

    decoded = page_text.replace('\\"', '"').replace("\\n", "\n").replace("\\u0026", "&")
    children = [_clean_text(match.group(1)) for match in re.finditer(r'"children"\s*:\s*"([^"]{12,})"', decoded)]
    return [block for block in children if _looks_like_article_text(block)]


def _looks_like_article_text(text: str) -> bool:
    """Keep likely article text, drop navigation and UI labels."""
    if not text or len(text) < 3:
        return False
    lower = text.lower()
    noisy = ("the motley fool", "join stock advisor", "premium investing services", "accessibility")
    return not any(fragment in lower for fragment in noisy)


def _split_transcript_sections(blocks: list[str]) -> tuple[list[str], list[str]]:
    """Split text blocks into prepared remarks and Q&A sections."""
    prepared: list[str] = []
    qa: list[str] = []
    current = "prepared"
    transcript_started = not any(FULL_TRANSCRIPT_HEADING_PATTERN.fullmatch(block) for block in blocks)
    saw_transcript_heading = False

    for block in blocks:
        normalized = block.strip().strip(":")
        if not saw_transcript_heading and normalized.lower() in {
            "contents",
            "prepared remarks",
            "questions and answers",
            "call participants",
        }:
            continue
        if FULL_TRANSCRIPT_HEADING_PATTERN.fullmatch(normalized):
            transcript_started = True
            saw_transcript_heading = True
            continue
        if not transcript_started:
            continue
        if PREPARED_HEADING_PATTERN.fullmatch(block.strip()):
            current = "prepared"
            saw_transcript_heading = True
            continue
        if QA_HEADING_PATTERN.fullmatch(normalized):
            current = "qa"
            saw_transcript_heading = True
            continue
        if STOP_HEADING_PATTERN.fullmatch(normalized):
            break
        if not saw_transcript_heading and _is_intro_block(block):
            continue
        if current == "prepared" and _is_interview_intro(block):
            prepared.append(block)
            current = "qa"
            continue
        if current == "prepared" and _is_qa_start(block):
            current = "qa"
        if current == "qa":
            qa.append(block)
        else:
            prepared.append(block)

    return prepared, qa


def _is_qa_start(block: str) -> bool:
    """Detect when an unheaded transcript moves from remarks to Q&A."""
    lower = block.lower()
    if "your next question" in lower:
        return True
    if any(
        fragment in lower
        for fragment in (
            "we will now open the call for questions",
            "head over to investor questions",
            "from say.com, the first question",
            "go to investor questions",
            "move on to analyst questions",
            "move over to analyst questions",
        )
    ):
        return True
    return bool(QA_START_PATTERN.search(block)) and ("operator:" in lower or "your line is open" in lower)


def _is_interview_intro(block: str) -> bool:
    """Detect Netflix-style earnings interview intro before Q&A-only content."""
    lower = block.lower()
    return "earnings interview" in lower and "joining me today" in lower


def _is_intro_block(block: str) -> bool:
    """Filter obvious article intro boilerplate before transcript sections."""
    lower = block.lower()
    intro_fragments = (
        "earnings call for the period",
        "contents:",
        "this article is a transcript",
        "image source:",
        "prepared remarks:",
        "question-and-answer session:",
    )
    return any(fragment in lower for fragment in intro_fragments)


def _split_interview_fallback(blocks: list[str]) -> tuple[list[str], list[str]]:
    """Fallback for interview-style Fool transcripts without explicit Q&A heading."""
    try:
        start_index = next(
            index + 1 for index, block in enumerate(blocks) if FULL_TRANSCRIPT_HEADING_PATTERN.fullmatch(block.strip())
        )
    except StopIteration:
        return [], []

    transcript_blocks: list[str] = []
    for block in blocks[start_index:]:
        normalized = block.strip().strip(":")
        if STOP_HEADING_PATTERN.fullmatch(normalized) or normalized.lower() in {
            "read next",
            "all earnings call transcripts",
            "call participants",
        }:
            break
        if _is_intro_block(block):
            continue
        transcript_blocks.append(block)

    if len(transcript_blocks) < 3:
        return [], []
    return [transcript_blocks[0]], transcript_blocks[1:]


def _build_segments(prepared: list[str], qa: list[str]) -> list[TranscriptSegment]:
    """Build speaker-aware transcript segments from text blocks."""
    segments: list[TranscriptSegment] = []
    for section_name, blocks in (("prepared_remarks", prepared), ("questions_and_answers", qa)):
        speaker: Optional[str] = None
        pending: list[str] = []
        for block in blocks:
            prefixed_speaker, prefixed_text = _split_speaker_prefix(block)
            if prefixed_speaker:
                if pending:
                    segments.append(TranscriptSegment(speaker=speaker, text="\n\n".join(pending), section=section_name))
                    pending = []
                speaker = prefixed_speaker
                if prefixed_text:
                    pending.append(prefixed_text)
                continue

            possible_speaker = _detect_speaker(block)
            if possible_speaker:
                if pending:
                    segments.append(TranscriptSegment(speaker=speaker, text="\n\n".join(pending), section=section_name))
                    pending = []
                speaker = possible_speaker
                continue
            pending.append(block)
        if pending:
            segments.append(TranscriptSegment(speaker=speaker, text="\n\n".join(pending), section=section_name))
    return segments


def _split_speaker_prefix(block: str) -> tuple[Optional[str], str]:
    """Split blocks like 'Operator: Welcome...' into speaker and text."""
    match = SPEAKER_PREFIX_PATTERN.match(block)
    if not match:
        return None, block
    return match.group(1), match.group(2).strip()


def _detect_speaker(block: str) -> Optional[str]:
    """Detect Motley Fool speaker blocks such as 'Tim Cook -- CEO'."""
    if len(block) > 90:
        return None
    if block.endswith(":"):
        return block.rstrip(":").strip()
    if " -- " in block:
        return block.strip()
    if re.fullmatch(r"[A-Z][A-Za-z .'-]{2,50}", block):
        return block.strip()
    return None


class MotleyFoolTranscriptService:
    """Fetch earnings call transcripts from The Motley Fool."""

    async def list_transcripts(self, ticker: str, limit: int = 8) -> EarningsCallTranscriptListResponse:
        """List recent Motley Fool earnings call transcript candidates for a ticker."""
        normalized_ticker = _normalize_ticker(ticker)
        logger.info("motley_fool_transcript_list_request", ticker=normalized_ticker, limit=limit)
        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout, proxy=_http_proxy()) as client:
            candidates = await self._find_candidates(normalized_ticker, limit, client=client, validate_pages=True)
        if not candidates:
            raise LookupError(f"No Motley Fool earnings call transcript found for {normalized_ticker}")
        return EarningsCallTranscriptListResponse(ticker=normalized_ticker, transcripts=candidates)

    async def get_latest_transcript(self, ticker: str, limit: int = 5) -> EarningsCallTranscriptResponse:
        """Find and parse the latest Motley Fool earnings call transcript for a ticker."""
        normalized_ticker = _normalize_ticker(ticker)
        logger.info("motley_fool_transcript_request", ticker=normalized_ticker, limit=limit)

        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout, proxy=_http_proxy()) as client:
            candidates = await self._find_candidates(normalized_ticker, limit, client=client)
            if not candidates:
                raise LookupError(f"No Motley Fool earnings call transcript found for {normalized_ticker}")

            errors: list[str] = []
            for candidate in candidates:
                try:
                    page_text = await _fetch_text(client, candidate.url)
                    transcript = self._parse_transcript(normalized_ticker, candidate, page_text, candidates)
                    logger.info("motley_fool_transcript_found", ticker=normalized_ticker, url=candidate.url)
                    return transcript
                except Exception as e:
                    logger.warning("motley_fool_transcript_parse_failed", ticker=normalized_ticker, url=candidate.url, error=str(e))
                    errors.append(str(e))

        raise LookupError(f"Motley Fool transcript candidates were found but could not be parsed: {errors[:3]}")

    async def get_transcript_by_url(self, ticker: str, url: str) -> EarningsCallTranscriptResponse:
        """Fetch and parse a specific Motley Fool transcript URL."""
        normalized_ticker = _normalize_ticker(ticker)
        normalized_url = _validate_transcript_url(url, normalized_ticker)
        candidate = TranscriptCandidate(
            title=_title_from_url(normalized_url),
            url=normalized_url,
            published_at=_candidate_published_at(normalized_url),
        )

        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout, proxy=_http_proxy()) as client:
            page_text = await _fetch_text(client, normalized_url)
            return self._parse_transcript(normalized_ticker, candidate, page_text, [candidate])

    async def _find_candidates(
        self,
        ticker: str,
        limit: int,
        client: Optional[httpx.AsyncClient] = None,
        validate_pages: bool = False,
    ) -> list[TranscriptCandidate]:
        """Find Motley Fool transcript candidates using quote pages and search fallback."""
        candidates: list[TranscriptCandidate] = []

        async def collect_from_quote_pages(http_client: httpx.AsyncClient) -> None:
            for exchange in QUOTE_EXCHANGES:
                quote_url = f"{FOOL_BASE_URL}/quote/{exchange}/{ticker.lower()}/"
                try:
                    quote_text = await _fetch_text(http_client, quote_url)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        continue
                    logger.warning("motley_fool_quote_fetch_failed", ticker=ticker, exchange=exchange, error=str(e))
                    continue
                except Exception as e:
                    logger.warning("motley_fool_quote_fetch_failed", ticker=ticker, exchange=exchange, error=str(e))
                    continue

                candidates.extend(_extract_quote_candidates(quote_text, ticker))
                if candidates:
                    break

        if client is None:
            timeout = httpx.Timeout(30.0, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout, proxy=_http_proxy()) as local_client:
                await collect_from_quote_pages(local_client)
        else:
            await collect_from_quote_pages(client)

        if not candidates:
            candidates.extend(await _search_duckduckgo(ticker, limit))

        candidates = _dedupe_candidates(candidates, limit)
        if validate_pages and client is not None:
            return await _filter_reachable_candidates(client, candidates, limit)
        return candidates

    def _parse_transcript(
        self,
        ticker: str,
        candidate: TranscriptCandidate,
        page_text: str,
        candidates: list[TranscriptCandidate],
    ) -> EarningsCallTranscriptResponse:
        """Parse transcript sections from a Motley Fool article page."""
        title = _extract_title(page_text, candidate.title)
        blocks = _extract_text_blocks(page_text)
        prepared, qa = _split_transcript_sections(blocks)
        if not qa:
            fallback_prepared, fallback_qa = _split_interview_fallback(blocks)
            if fallback_qa:
                prepared, qa = fallback_prepared, fallback_qa

        if not qa:
            raise ValueError("q_and_a_section_not_found")
        if not prepared:
            raise ValueError("prepared_remarks_not_found")

        segments = _build_segments(prepared, qa)
        return EarningsCallTranscriptResponse(
            ticker=ticker,
            title=title,
            url=candidate.url,
            published_date=_extract_published_date(candidate.url, page_text),
            prepared_remarks="\n\n".join(prepared),
            questions_and_answers="\n\n".join(qa),
            segments=segments,
            candidates=TypeAdapter(list[TranscriptCandidate]).validate_python(candidates),
        )


motley_fool_transcript_service = MotleyFoolTranscriptService()
