"""测试夹具：从 tests/fixtures/quant_research 读 4 只股票（2026-09-30 拉取）的 FMP 原始响应。"""

import json
from datetime import date
from pathlib import Path

from app.services.quant_research.inputs import StockInputs, build_inputs

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "quant_research"
AS_OF = date(2026, 9, 30)
SECTORS = {"NVDA": "information_technology", "JPM": "financials", "O": "real_estate", "XOM": "energy"}


def raw(symbol: str, name: str):
    return json.loads((FIXTURE_DIR / f"{symbol}.{name}.json").read_text())


def load_inputs(symbol: str) -> StockInputs:
    return build_inputs(
        symbol=symbol,
        as_of=AS_OF,
        sector_key=SECTORS[symbol],
        income=raw(symbol, "isq"),
        cash=raw(symbol, "cfq"),
        balance=raw(symbol, "bsq"),
        estimates=raw(symbol, "est"),
        prices=raw(symbol, "px"),
        name=raw(symbol, "profile")[0].get("companyName"),
    )
