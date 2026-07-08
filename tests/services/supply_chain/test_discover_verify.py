"""Discovery and verification unit tests."""

from app.services.supply_chain.discover import DiscoveryResult, discover_suppliers
from app.services.supply_chain.verify import relevant_fragments


class FakeLLM:
    """Structured-output fake."""

    async def call(self, messages, **kwargs):
        return {"suppliers": [{"supplier_name": "TSMC", "product_text": "foundry", "confidence": 88}], "customers": [{"customer_name": "Microsoft", "product_text": "GPU", "confidence": 75}], "skipped": False}


async def test_discovery_parses_suppliers_and_customers() -> None:
    """One structured call returns both directions."""
    result = await discover_suppliers("NVDA", FakeLLM())
    assert isinstance(result, DiscoveryResult)
    assert result.suppliers[0].supplier_name == "TSMC"
    assert result.customers[0].customer_name == "Microsoft"


def test_relevant_fragments_never_sends_whole_document() -> None:
    """Evidence extraction returns bounded keyword windows."""
    text = "x" * 2000 + "TSMC supplies wafers" + "y" * 2000
    fragments = relevant_fragments(text, ["TSMC"])
    assert len(fragments) == 1
    assert len(fragments[0]) <= 500
