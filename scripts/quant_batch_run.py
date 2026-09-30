"""本地手动跑一次美股量化研究批量（默认只跑指定板块，受批量 FMP 额度约束）。

用法：PYTHONPATH=. uv run python scripts/quant_batch_run.py --sectors information_technology,energy
      PYTHONPATH=. uv run python scripts/quant_batch_run.py --all
"""

import argparse
import asyncio
from datetime import date

import httpx

from app.services.quant_research.batch import dump_summary, run_us_batch


async def main() -> None:
    """解析参数并运行批量。"""
    ap = argparse.ArgumentParser()
    ap.add_argument("--sectors", default="information_technology,energy")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--as-of", default=date.today().isoformat())
    args = ap.parse_args()
    sectors = None if args.all else set(args.sectors.split(","))
    async with httpx.AsyncClient() as client:
        summary = await run_us_batch(date.fromisoformat(args.as_of), redis=None, client=client, sectors=sectors)
    print(dump_summary(summary))


if __name__ == "__main__":
    asyncio.run(main())
