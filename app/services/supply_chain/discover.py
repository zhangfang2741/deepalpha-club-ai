"""LLM discovery of suppliers and customers."""

import json
import re
from typing import Any, Protocol

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings


class ProductDetail(BaseModel):
    """A concrete supplied product with graph and detail labels."""

    short_name: str
    full_name: str = ""
    full_name_zh: str = ""
    description: str = ""
    description_zh: str = ""


class SupplyRelation(BaseModel):
    """Discovered relation payload."""

    supplier_name: str | None = None
    supplier_name_zh: str | None = None
    supplier_ticker: str | None = None
    customer_name: str | None = None
    customer_name_zh: str | None = None
    customer_ticker: str | None = None
    product_text: str = ""
    products: list[ProductDetail] = Field(default_factory=list)
    rationale: str = ""
    relationship_description: str = ""
    relationship_description_zh: str = ""
    confidence: int = Field(default=70, ge=0, le=100)
    is_single_source: bool = False
    info_year: int | None = None

    @field_validator("supplier_ticker", "customer_ticker")
    @classmethod
    def normalize_ticker(cls, value: str | None) -> str | None:
        """Normalize plausible US ticker symbols and reject prose."""
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized if re.fullmatch(r"[A-Z][A-Z0-9.-]{0,7}", normalized) else None

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value: object) -> object:
        """Accept either a 0-1 score or an integer percentage."""
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            numeric = float(value)
            return round(numeric * 100) if 0 <= numeric <= 1 else round(numeric)
        return value


class DiscoveryResult(BaseModel):
    """Structured discovery output."""

    suppliers: list[SupplyRelation] = Field(default_factory=list)
    customers: list[SupplyRelation] = Field(default_factory=list)
    company_name_zh: str | None = None
    skipped: bool = False
    skip_reason: str | None = None

    @field_validator("suppliers", "customers")
    @classmethod
    def rank_relations(cls, value: list[SupplyRelation]) -> list[SupplyRelation]:
        return sorted(value, key=lambda relation: relation.confidence, reverse=True)


class StructuredLLM(Protocol):
    """Minimal injectable LLM protocol."""

    async def call(self, messages: Any, **kwargs: Any) -> Any: ...


def discovery_prompt(ticker: str) -> str:
    """Return the shared discovery prompt for structured and streaming calls."""
    return f"""You are building an investment-grade supply chain graph for {ticker.upper()}.
Return all and only the company's genuinely core direct suppliers and major customers, with no more than
5 suppliers and 5 customers. A core supplier must provide a strategically critical component, scarce input,
material share of production, or a dependency whose disruption would materially affect operations.
A major customer must represent material revenue, shipment volume, a disclosed concentration, or a
strategic purchasing relationship. Exclude incidental vendors, generic cloud/software providers,
ordinary distributors, speculative associations, and names included merely to fill the list.
For every relation include the US-listed ticker when known: supplier_ticker for suppliers and
customer_ticker for customers. Use null for private companies, non-US listings, or uncertain symbols.
Never return multiple entries with the same ticker. Prefer the primary US-listed common-stock ticker over
OTC symbols. For example, TSMC is TSM, not SMECF. Include product_text plus a products list. Each product must contain short_name
(a concise industry abbreviation such as HBM3, EUV, LFP, 4N LiOH; no more than 12 characters),
full_name, full_name_zh, description, and description_zh. Both descriptions explain in plain language
what the product is and how the target company uses it in one concise sentence. Include at most 2 products
per relation; keep every description and rationale concise. Chinese fields must be natural Simplified Chinese.
Also include a rationale explaining why the relationship is core. Add relationship_description and
relationship_description_zh with a detailed explanation of how the listed products connect the supplier
and customer operationally, where they are used, and why the relationship matters to both companies.
fact-certainty confidence 0-100, single-source status, and information year. Confidence measures
factual certainty, not commercial importance. Rank each list by importance and evidence strength.
Also return company_name_zh for the target company, supplier_name_zh for every supplier, and
customer_name_zh for every customer. Use the established Simplified Chinese company name when one
exists; otherwise provide a concise, faithful Chinese translation.
If no genuinely core relationship is known, return an empty list; if knowledge of the company is
insufficient overall return skipped=true. Never invent names and never pad either list."""


async def discover_suppliers(ticker: str, llm: StructuredLLM) -> DiscoveryResult:
    """Discover direct upstream and downstream relations in one structured call."""
    prompt = discovery_prompt(ticker)
    result = await llm.call(
        [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Discover the direct supply-chain relationships for {ticker.upper()}."},
        ],
        model_name=settings.SUPPLY_CHAIN_DISCOVER_MODEL or None,
        response_format=DiscoveryResult,
    )
    parsed = result if isinstance(result, DiscoveryResult) else DiscoveryResult.model_validate(result)
    if parsed.skipped or parsed.suppliers or parsed.customers:
        return parsed
    raw = await llm.call(
        [
            {
                "role": "system",
                "content": f"{prompt}\nReturn JSON only with keys company_name_zh, suppliers, customers, skipped, skip_reason. Supplier items use supplier_name and supplier_name_zh; customer items use customer_name and customer_name_zh. Every relation includes relationship_description, relationship_description_zh and products with short_name, full_name, full_name_zh, description, description_zh.",
            },
            {"role": "user", "content": f"Return the supply-chain JSON for {ticker.upper()}."},
        ],
        model_name=settings.SUPPLY_CHAIN_DISCOVER_MODEL or None,
    )
    content = raw.content if hasattr(raw, "content") else raw
    if isinstance(content, list):
        content = "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content)
    match = re.search(r"\{.*\}", str(content), re.DOTALL)
    if match is None:
        return DiscoveryResult(skipped=True, skip_reason="model returned no parseable JSON")
    return DiscoveryResult.model_validate(json.loads(match.group(0)))
