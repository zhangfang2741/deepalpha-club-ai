"""FMP universe loading and deterministic company-name matching."""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

import httpx

from app.core.config import settings
from app.services.supply_chain.alias_resolver import normalize_alias

_COMPANY_SUFFIXES = {
    "ag",
    "co",
    "com",
    "company",
    "corp",
    "corporation",
    "group",
    "holding",
    "holdings",
    "inc",
    "incorporated",
    "limited",
    "ltd",
    "nv",
    "plc",
    "sa",
}


def _match_name(value: str) -> str:
    """Reduce display names and model-added qualifiers to matching tokens."""
    normalized = normalize_alias(value).lower()
    normalized = re.sub(r"\([^)]*\)", " ", normalized)
    normalized = re.sub(r"\.com\b", " ", normalized)
    tokens = re.findall(r"[a-z0-9]+", normalized)
    return " ".join(token for token in tokens if token not in _COMPANY_SUFFIXES)


@dataclass(frozen=True)
class ListedCompany:
    """Minimal listed company record."""

    symbol: str
    name: str
    exchange: str = ""
    market_cap: float | None = None


class FMPUniverse:
    """In-memory name/symbol index, injectable in tests."""

    def __init__(self, companies: list[ListedCompany] | None = None) -> None:
        self.companies = companies or []
        self._symbol_index: dict[str, ListedCompany] = {}
        self._name_index: dict[str, ListedCompany] = {}
        self._token_index: dict[str, list[ListedCompany]] = {}
        self._reindex()

    def _reindex(self) -> None:
        """Build constant-time indexes and small fuzzy candidate buckets."""
        self._symbol_index = {company.symbol.lower(): company for company in self.companies}
        self._name_index = {}
        self._token_index = {}
        for company in self.companies:
            matched_name = _match_name(company.name)
            self._name_index.setdefault(matched_name, company)
            if matched_name:
                self._token_index.setdefault(matched_name.split()[0], []).append(company)

    async def load(self) -> list[ListedCompany]:
        """Load US-listed companies from FMP once per instance."""
        if self.companies or not settings.FMP_API_KEY:
            return self.companies
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://financialmodelingprep.com/stable/stock-list", params={"apikey": settings.FMP_API_KEY}
            )
            response.raise_for_status()
        allowed = {"NASDAQ", "NYSE", "AMEX"}
        self.companies = []
        for item in response.json():
            exchange = str(item.get("exchange") or item.get("exchangeShortName") or "").upper()
            if exchange and exchange not in allowed:
                continue
            symbol = str(item["symbol"]).upper()
            name = str(item.get("companyName") or item.get("name") or symbol)
            self.companies.append(ListedCompany(symbol, name, exchange))
        self._reindex()
        return self.companies

    def match(self, name: str) -> ListedCompany | None:
        """Match by ticker, canonical name, then conservative fuzzy score."""
        canonical = _match_name(name)
        exact = self._symbol_index.get(canonical) or self._name_index.get(canonical)
        if exact is not None:
            return exact
        candidates = self._token_index.get(canonical.split()[0], []) if canonical else []
        raw_name = normalize_alias(name).lower()
        scored = [
            (
                max(
                    SequenceMatcher(None, canonical, _match_name(company.name)).ratio(),
                    SequenceMatcher(None, raw_name, normalize_alias(company.name).lower()).ratio(),
                ),
                company,
            )
            for company in candidates
        ]
        score, company = max(scored, default=(0.0, None), key=lambda item: item[0])
        return company if score >= 0.84 else None


def company_from_payload(payload: dict[str, Any]) -> ListedCompany:
    """Convert a cached/API payload into a typed record."""
    return ListedCompany(
        symbol=str(payload["symbol"]).upper(),
        name=str(payload.get("companyName") or payload.get("name") or payload["symbol"]),
        exchange=str(payload.get("exchange") or payload.get("exchangeShortName") or ""),
        market_cap=float(payload["marketCap"]) if payload.get("marketCap") is not None else None,
    )
