"""从 data/quant_seed/2026-09-30 生成 golden 测试用的板块分布（只保存测试用到的 4 个板块 + 综合分分布）。

种子数据没有现金流 / 资产负债表，依赖它们的指标（P/B、EV 类、ROE 等）用当时拉到的 FMP
ratios / key-metrics 近似回填 —— 只用于测试分布，不影响线上计算。
用法：PYTHONPATH=. uv run python scripts/quant_make_test_distributions.py
"""

import json
from datetime import date
from pathlib import Path

from app.services.quant_research.builder import evaluate
from app.services.quant_research.inputs import build_inputs
from app.services.quant_research.metrics import MetricValue, compute_metrics
from app.services.quant_research.scoring import build_distributions
from app.services.quant_research.universe import GICS_SECTORS

SEED = Path("data/quant_seed/2026-09-30")
OUT = Path("tests/fixtures/quant_research/distributions.json")
AS_OF = date(2026, 9, 30)
KEEP = {"information_technology", "financials", "real_estate", "energy"}
_WIKI_TO_KEY = {v[0]: k for k, v in GICS_SECTORS.items()}


def _load(sym: str, name: str):
    p = SEED / "raw" / f"{sym}.{name}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    return None if isinstance(d, dict) else d


def _backfill(m: dict[str, MetricValue], ratios: dict, km: dict) -> None:
    def put(key, v):
        if m[key].status == "missing" and v is not None:
            m[key] = MetricValue(float(v), "ok" if v > 0 or key in ("roe", "roa", "roic", "fcf_m") else "not_meaningful")

    put("pb", ratios.get("priceToBookRatioTTM"))
    put("pcf", ratios.get("priceToOperatingCashFlowRatioTTM"))
    put("ev_sales_ttm", km.get("evToSalesTTM"))
    put("ev_ebitda_ttm", km.get("evToEBITDATTM"))
    put("roe", km.get("returnOnEquityTTM"))
    put("roa", km.get("returnOnAssetsTTM"))
    put("roic", km.get("returnOnInvestedCapitalTTM"))
    fcf, rev = ratios.get("freeCashFlowPerShareTTM"), ratios.get("revenuePerShareTTM")
    if fcf is not None and rev:
        put("fcf_m", fcf / rev)


def main() -> None:
    """生成并写出分布文件。"""
    universe = json.loads((SEED / "universe.json").read_text())
    sectors = {u["symbol"]: _WIKI_TO_KEY.get(u["sector"]) for u in universe}
    metrics_all: dict[str, tuple[str, dict[str, MetricValue]]] = {}
    inputs = {}
    for sym, sector in sectors.items():
        if not sector:
            continue
        inp = build_inputs(symbol=sym, as_of=AS_OF, sector_key=sector, income=_load(sym, "isq"), cash=[],
                           balance=None, estimates=_load(sym, "est"), prices=_load(sym, "px"))
        m = compute_metrics(inp)
        _backfill(m, (_load(sym, "ratios") or [{}])[0], (_load(sym, "km") or [{}])[0])
        metrics_all[sym] = (sector, m)
        inputs[sym] = inp
    dists = build_distributions(metrics_all)
    composites = []
    for sym in metrics_all:
        ev = evaluate(inputs[sym], [], dists)
        if ev.composite is not None:
            composites.append(ev.composite)
    out = {f"{s}|{k}": v for (s, k), v in dists.items() if s in KEEP}
    out["_all|_overall"] = sorted(composites)
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {OUT} keys={len(out)} composites={len(composites)} size={OUT.stat().st_size // 1024}KB")


if __name__ == "__main__":
    main()
