"""Multi-source evidence verification."""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.models.supply_chain_clue import SupplyChainClue
from app.models.supply_chain_edge import SupplyChainEdge
from app.services.supply_chain.domain import GiraffeEdge


@dataclass(frozen=True)
class EvidenceSnippet:
    """A compact relevant source fragment."""

    text: str
    source_type: str
    document_url: str = ""
    section: str | None = None
    filing_date: date | None = None


class EvidenceProvider(Protocol):
    """Injectable evidence source."""

    async def fetch(self, edge: GiraffeEdge) -> list[EvidenceSnippet]: ...


class ExtractedClue(BaseModel):
    """LLM-extracted stance clue."""

    snippet: str
    stance: str
    source_type: str
    document_url: str = ""
    section: str | None = None
    filing_date: date | None = None
    confidence_delta: int | None = None


class VerificationResult(BaseModel):
    """Verification scoring output."""

    clues: list[ExtractedClue] = Field(default_factory=list)
    confidence: int = Field(ge=0, le=100)
    evidence_summary: str = ""


def relevant_fragments(text: str, keywords: list[str], limit: int = 3, width: int = 500) -> list[str]:
    """Extract bounded keyword windows before any LLM invocation."""
    lowered = text.lower()
    fragments = []
    for keyword in keywords:
        start = lowered.find(keyword.lower())
        if start >= 0:
            fragments.append(text[max(0, start - width // 2) : start + width // 2])
        if len(fragments) >= limit:
            break
    return fragments


async def verify_edges(
    edges: list[GiraffeEdge],
    session: Session,
    llm: Any,
    providers: list[EvidenceProvider],
    run_id: uuid.UUID | None = None,
) -> int:
    """Collect all sources independently, append clues, and rescore edges."""
    verified = 0
    for edge in edges:
        evidence: list[EvidenceSnippet] = []
        for provider in providers:
            evidence.extend(await provider.fetch(edge))
        row = session.exec(select(SupplyChainEdge).where(SupplyChainEdge.edge_id == str(edge.edge_id))).first()
        if row is None:
            continue
        if not evidence:
            row.confidence_source = "UNVERIFIED"
            row.properties = {**row.properties, "confidence_source": "UNVERIFIED"}
            continue
        result = await llm.call(
            [{"role": "system", "content": "Assess supplied evidence. Return stance clues and a calibrated factual confidence."}, {"role": "user", "content": str([item.__dict__ for item in evidence])}],
            response_format=VerificationResult,
        )
        result = result if isinstance(result, VerificationResult) else VerificationResult.model_validate(result)
        source_count = len({clue.source_type for clue in result.clues})
        confidence_source = "MULTI_SOURCE_VERIFIED" if source_count > 1 else "SEC_VERIFIED"
        for clue in result.clues:
            session.add(SupplyChainClue(edge_id=str(edge.edge_id), node_id=str(edge.src_id), source_type=clue.source_type, document_url=clue.document_url, section=clue.section, filing_date=clue.filing_date, snippet_text=clue.snippet, stance=clue.stance, confidence_delta=clue.confidence_delta, run_id=run_id))
        row.confidence = result.confidence
        row.confidence_source = confidence_source
        row.properties = {**row.properties, "confidence": result.confidence, "confidence_source": confidence_source, "evidence_summary": result.evidence_summary}
        verified += 1
    session.commit()
    return verified
