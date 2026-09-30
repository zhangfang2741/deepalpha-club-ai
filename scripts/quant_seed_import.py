"""把 2026-09-30 拉取的标普1500 一致预期导入为 quant_estimate_snapshots 的第一天（幂等，只补不覆盖）。

EPS 修正需要前后快照对比，导入后积累期从 2026-09-30 起算。
用法（导入到 .env.<ENV> 指向的库）：PYTHONPATH=. uv run python scripts/quant_seed_import.py
"""

import asyncio
import json
from datetime import date
from pathlib import Path

from app.services.quant_research.batch import estimate_rows
from app.services.quant_research.repository import insert_estimates

SEED = Path("data/quant_seed/2026-09-30/raw")
SNAPSHOT_DATE = date(2026, 9, 30)


async def main() -> None:
    """导入首份快照。"""
    rows: list[dict] = []
    for f in sorted(SEED.glob("*.est.json")):
        data = json.loads(f.read_text())
        if isinstance(data, list):
            rows.extend(estimate_rows("us", f.name.split(".")[0], SNAPSHOT_DATE, data))
    inserted = await insert_estimates(rows)
    print(f"rows={len(rows)} inserted={inserted}")


if __name__ == "__main__":
    asyncio.run(main())
