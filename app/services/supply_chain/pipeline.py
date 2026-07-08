"""Single-company supply-chain pipeline orchestration."""

import uuid
from typing import Any

from sqlmodel import Session

from app.services.supply_chain.discover import DiscoveryResult, discover_suppliers
from app.services.supply_chain.filter import select_edges_to_verify
from app.services.supply_chain.fmp_universe import FMPUniverse
from app.services.supply_chain.resolve import resolve_suppliers
from app.services.supply_chain.verify import EvidenceProvider, verify_edges


async def run_company_pipeline(
    ticker: str,
    run_id: uuid.UUID,
    session: Session,
    llm: Any,
    universe: FMPUniverse,
    providers: list[EvidenceProvider] | None = None,
) -> dict[str, Any]:
    """Run discover, resolve, candidate filter, and evidence verification."""
    await universe.load()
    discovered: DiscoveryResult = await discover_suppliers(ticker, llm)
    if discovered.skipped:
        return {"skipped": True, "skip_reason": discovered.skip_reason}
    graph = resolve_suppliers(ticker, discovered, session, universe, run_id)
    candidates = select_edges_to_verify(ticker, session)
    verified = await verify_edges(candidates, session, llm, providers or [], run_id)
    return {"skipped": False, "suppliers": len(discovered.suppliers), "customers": len(discovered.customers), "edges": len(graph.edges), "verified": verified}
