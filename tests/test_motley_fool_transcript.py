"""Motley Fool transcript service tests."""

from datetime import date

import pytest

from app.services.motley_fool import (
    MotleyFoolTranscriptService,
    _candidate_published_at,
    _extract_quote_candidates,
    _normalize_ticker,
    _validate_transcript_url,
)
from app.schemas.motley_fool import TranscriptCandidate


QUOTE_HTML = r"""
<html>
  <script>
    self.__next_f.push([1,"{\"path\":\"/earnings/call-transcripts/2026/05/28/nvidia-nvda-q1-2027-earnings-call-transcript/\",\"headline\":\"Nvidia (NVDA) Q1 2027 Earnings Call Transcript\"}"])
  </script>
</html>
"""

TRANSCRIPT_HTML = """
<!doctype html>
<html>
  <head>
    <title>Nvidia (NVDA) Q1 2027 Earnings Call Transcript | The Motley Fool</title>
    <meta property="article:published_time" content="2026-05-28T21:30:00Z">
  </head>
  <body>
    <article>
      <p>Image source: The Motley Fool.</p>
      <h2>Prepared Remarks:</h2>
      <p>Operator</p>
      <p>Good afternoon, and welcome to Nvidia's quarterly earnings call.</p>
      <p>Jensen Huang -- Chief Executive Officer</p>
      <p>Revenue grew strongly as demand for accelerated computing expanded.</p>
      <h2>Question-and-Answer Session</h2>
      <p>Operator</p>
      <p>Our first question comes from Analyst One.</p>
      <p>Analyst One -- Bank</p>
      <p>Can you discuss supply constraints?</p>
      <p>Jensen Huang -- Chief Executive Officer</p>
      <p>We continue to add capacity with our partners.</p>
      <h2>Stocks Mentioned</h2>
      <p>Nvidia</p>
    </article>
  </body>
</html>
"""

CURRENT_STYLE_TRANSCRIPT_HTML = """
<!doctype html>
<html>
  <head>
    <title>Nvidia (NVDA) Q1 2027 Earnings Transcript | The Motley Fool</title>
  </head>
  <body>
    <h2>TAKEAWAYS</h2>
    <p>Summary text that should not be part of the transcript.</p>
    <h2>Full Conference Call Transcript</h2>
    <p><strong>Toshiya Hari:</strong> Welcome to NVIDIA's conference call.</p>
    <p><strong>Colette Kress:</strong> Revenue reached a record level.</p>
    <p><strong>Operator:</strong> Your first question comes from Analyst One. Your line is open.</p>
    <p><strong>Analyst One:</strong> Thanks for taking my question.</p>
    <p><strong>Jen-Hsun Huang:</strong> We are expanding capacity.</p>
  </body>
</html>
"""

CONTENTS_STYLE_TRANSCRIPT_HTML = """
<!doctype html>
<html>
  <head>
    <title>Nvidia (NVDA) Q3 2025 Earnings Call Transcript | The Motley Fool</title>
  </head>
  <body>
    <p>Contents:</p>
    <p>Prepared Remarks</p>
    <p>Questions and Answers</p>
    <p>Call Participants</p>
    <h2>Prepared Remarks:</h2>
    <p>Operator</p>
    <p>Good afternoon. Welcome to the earnings call.</p>
    <p>After the speakers' remarks, there will be a question-and-answer session.</p>
    <p>Colette Kress -- Chief Financial Officer</p>
    <p>Revenue was a record for the quarter.</p>
    <h2>Questions & Answers:</h2>
    <p>[Operator instructions] Your first question comes from Analyst One.</p>
    <p>Analyst One -- Bank</p>
    <p>Can you discuss Blackwell demand?</p>
    <p>Jensen Huang -- Chief Executive Officer</p>
    <p>Demand remains very strong.</p>
  </body>
</html>
"""

SAY_QUESTIONS_TRANSCRIPT_HTML = """
<!doctype html>
<html>
  <head>
    <title>Tesla (TSLA) Q4 2025 Earnings Call Transcript | The Motley Fool</title>
  </head>
  <body>
    <h2>Full Conference Call Transcript</h2>
    <p>Elon Musk: We are making big investments for the future.</p>
    <p>Vaibhav Taneja: Revenue and margins improved sequentially.</p>
    <p>Travis Axelrod: Now we're going to head over to investor questions. The first question is about robotaxi ambition.</p>
    <p>Elon Musk: The future is autonomous.</p>
    <p>Travis Axelrod: We're going to move on to analyst questions. The first analyst is from Wolfe Research.</p>
    <p>Emmanuel Rosner: Can you discuss capex?</p>
  </body>
</html>
"""

INTERVIEW_TRANSCRIPT_HTML = """
<!doctype html>
<html>
  <head>
    <title>Netflix (NFLX) Q2 2025 Earnings Call Transcript | The Motley Fool</title>
  </head>
  <body>
    <h2>Full Conference Call Transcript</h2>
    <p>Spencer Wang: Good afternoon, and welcome to the Netflix Q2 2025 earnings interview. Joining me today are Co-CEOs and CFO.</p>
    <p>Is this due to better underlying revenue growth?</p>
    <p>Spencer Neumann: We increased our full-year revenue guidance.</p>
    <p>Spencer Wang: We will take our next question from Barton Crockett.</p>
    <p>Why is operating margin guidance for the full year only 30%?</p>
  </body>
</html>
"""


def test_normalize_ticker_accepts_us_symbols():
    """Normalize common US ticker inputs."""
    assert _normalize_ticker(" nvda ") == "NVDA"
    assert _normalize_ticker("brk/b") == "BRK.B"


def test_normalize_ticker_rejects_invalid_symbols():
    """Reject unsafe ticker input."""
    with pytest.raises(ValueError):
        _normalize_ticker("NVDA<script>")


def test_extract_quote_candidates_finds_transcript_paths():
    """Extract transcript paths from Fool quote HTML."""
    candidates = _extract_quote_candidates(QUOTE_HTML, "NVDA")

    assert len(candidates) == 1
    assert candidates[0].url == (
        "https://www.fool.com/earnings/call-transcripts/2026/05/28/"
        "nvidia-nvda-q1-2027-earnings-call-transcript/"
    )
    assert candidates[0].title == "Nvidia Nvda Q1 2027 Earnings Call Transcript"
    assert candidates[0].published_at is not None
    assert candidates[0].published_at.date().isoformat() == "2026-05-28"


def test_candidate_published_at_reads_motley_fool_url_date():
    """Read publish date from Motley Fool transcript URLs."""
    published_at = _candidate_published_at(
        "https://www.fool.com/earnings/call-transcripts/2026/05/20/nvidia-nvda-q1-2027-earnings-transcript/"
    )

    assert published_at is not None
    assert published_at.date().isoformat() == "2026-05-20"


def test_validate_transcript_url_rejects_non_matching_url():
    """Reject URLs outside Fool transcript pages or mismatched tickers."""
    valid = _validate_transcript_url(
        "https://www.fool.com/earnings/call-transcripts/2026/05/20/nvidia-nvda-q1-2027-earnings-transcript/",
        "NVDA",
    )

    assert valid.endswith("/nvidia-nvda-q1-2027-earnings-transcript/")
    with pytest.raises(ValueError):
        _validate_transcript_url("https://example.com/earnings/call-transcripts/nvda/", "NVDA")
    with pytest.raises(ValueError):
        _validate_transcript_url(
            "https://www.fool.com/earnings/call-transcripts/2026/05/20/nvidia-nvda-q1-2027-earnings-transcript/",
            "AAPL",
        )


def test_parse_transcript_splits_prepared_remarks_and_q_and_a():
    """Split transcript text into prepared remarks and Q&A."""
    service = MotleyFoolTranscriptService()
    candidate = TranscriptCandidate(
        title="Nvidia (NVDA) Q1 2027 Earnings Call Transcript",
        url="https://www.fool.com/earnings/call-transcripts/2026/05/28/nvidia-nvda-q1-2027-earnings-call-transcript/",
    )

    response = service._parse_transcript("NVDA", candidate, TRANSCRIPT_HTML, [candidate])

    assert response.ticker == "NVDA"
    assert response.published_date == date(2026, 5, 28)
    assert "Revenue grew strongly" in response.prepared_remarks
    assert "Can you discuss supply constraints?" in response.questions_and_answers
    assert "Stocks Mentioned" not in response.questions_and_answers
    assert any(segment.speaker == "Jensen Huang -- Chief Executive Officer" for segment in response.segments)


def test_parse_current_motley_fool_transcript_without_q_and_a_heading():
    """Split current Fool transcript pages using first-question cue."""
    service = MotleyFoolTranscriptService()
    candidate = TranscriptCandidate(
        title="Nvidia (NVDA) Q1 2027 Earnings Transcript",
        url="https://www.fool.com/earnings/call-transcripts/2026/05/20/nvidia-nvda-q1-2027-earnings-transcript/",
    )

    response = service._parse_transcript("NVDA", candidate, CURRENT_STYLE_TRANSCRIPT_HTML, [candidate])

    assert "Summary text" not in response.prepared_remarks
    assert "Revenue reached a record level" in response.prepared_remarks
    assert "Your first question comes from Analyst One" in response.questions_and_answers
    assert response.segments[0].speaker == "Toshiya Hari"


def test_parse_contents_style_transcript_skips_table_of_contents():
    """Skip Fool table-of-contents labels before the real transcript headings."""
    service = MotleyFoolTranscriptService()
    candidate = TranscriptCandidate(
        title="Nvidia (NVDA) Q3 2025 Earnings Call Transcript",
        url="https://www.fool.com/earnings/call-transcripts/2024/11/20/nvidia-nvda-q3-2025-earnings-call-transcript/",
    )

    response = service._parse_transcript("NVDA", candidate, CONTENTS_STYLE_TRANSCRIPT_HTML, [candidate])

    assert "Revenue was a record" in response.prepared_remarks
    assert "Can you discuss Blackwell demand?" in response.questions_and_answers
    assert "Call Participants" not in response.prepared_remarks


def test_parse_say_questions_transcript_detects_investor_questions():
    """Split Tesla-style say.com and analyst questions into Q&A."""
    service = MotleyFoolTranscriptService()
    candidate = TranscriptCandidate(
        title="Tesla (TSLA) Q4 2025 Earnings Call Transcript",
        url="https://www.fool.com/earnings/call-transcripts/2026/01/28/tesla-tsla-q4-2025-earnings-call-transcript/",
    )

    response = service._parse_transcript("TSLA", candidate, SAY_QUESTIONS_TRANSCRIPT_HTML, [candidate])

    assert "Revenue and margins improved" in response.prepared_remarks
    assert "robotaxi ambition" in response.questions_and_answers
    assert "Can you discuss capex?" in response.questions_and_answers


def test_parse_say_questions_transcript_detects_from_say_dot_com():
    """Split Tesla-style transcripts that start Q&A with a say.com cue."""
    service = MotleyFoolTranscriptService()
    candidate = TranscriptCandidate(
        title="Tesla (TSLA) Q3 2025 Earnings Call Transcript",
        url="https://www.fool.com/earnings/call-transcripts/2025/10/22/tesla-tsla-q3-2025-earnings-call-transcript/",
    )
    html = SAY_QUESTIONS_TRANSCRIPT_HTML.replace(
        "Now we're going to head over to investor questions. The first question is about robotaxi ambition.",
        "From say.com, the first question is about robotaxi ambition.",
    )

    response = service._parse_transcript("TSLA", candidate, html, [candidate])

    assert "robotaxi ambition" in response.questions_and_answers


def test_parse_interview_transcript_uses_intro_as_prepared_remarks():
    """Split Netflix-style earnings interviews into intro and Q&A."""
    service = MotleyFoolTranscriptService()
    candidate = TranscriptCandidate(
        title="Netflix (NFLX) Q2 2025 Earnings Call Transcript",
        url="https://www.fool.com/earnings/call-transcripts/2025/07/17/netflix-nflx-q2-2025-earnings-call-transcript/",
    )

    response = service._parse_transcript("NFLX", candidate, INTERVIEW_TRANSCRIPT_HTML, [candidate])

    assert "earnings interview" in response.prepared_remarks
    assert "underlying revenue growth" in response.questions_and_answers
    assert "operating margin guidance" in response.questions_and_answers


def test_parse_interview_transcript_fallback_without_intro():
    """Fallback to first transcript block as intro when interview headings are absent."""
    service = MotleyFoolTranscriptService()
    candidate = TranscriptCandidate(
        title="Netflix (NFLX) Q1 2026 Earnings Call Transcript",
        url="https://www.fool.com/earnings/call-transcripts/2026/04/16/netflix-nflx-q1-2026-earnings-call-transcript/",
    )
    html = """
    <html>
      <body>
        <h2>Full Conference Call Transcript</h2>
        <p>Gregory Peters: Perhaps I can kick this one off with a high-level framing.</p>
        <p>Spencer Wong: Following up on that question, what have been your biggest learnings?</p>
        <p>Theodore Sarandos: We are confident in the core business.</p>
      </body>
    </html>
    """

    response = service._parse_transcript("NFLX", candidate, html, [candidate])

    assert "high-level framing" in response.prepared_remarks
    assert "Following up on that question" in response.questions_and_answers
