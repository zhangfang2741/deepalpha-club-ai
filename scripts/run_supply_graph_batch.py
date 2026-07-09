"""Create and optionally monitor a supply-chain graph batch run."""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


console = Console()


@dataclass(frozen=True)
class BatchOptions:
    """CLI options for creating a supply-chain graph batch."""

    api_base: str
    universe: str
    watch: bool
    interval: float
    timeout: float


def parse_args() -> BatchOptions:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Run supply-chain graph batch jobs through the local API.")
    parser.add_argument(
        "--api-base",
        default="http://localhost:8000",
        help="API base URL, default: http://localhost:8000",
    )
    parser.add_argument(
        "--universe",
        default="sp500",
        choices=["sp500", "nasdaq100", "russell1000", "all"],
        help="Ticker universe to run, default: sp500",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Poll run detail until the run reaches a terminal status.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=10,
        help="Polling interval in seconds when --watch is enabled, default: 10",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30,
        help="HTTP timeout in seconds, default: 30",
    )
    args = parser.parse_args()
    return BatchOptions(
        api_base=args.api_base.rstrip("/"),
        universe=args.universe,
        watch=args.watch,
        interval=max(args.interval, 2),
        timeout=args.timeout,
    )


def create_run(client: httpx.Client, options: BatchOptions) -> str:
    """Create one batch run and return its run id."""
    response = client.post(
        f"{options.api_base}/api/v1/supply-graph/runs",
        json={"universe": options.universe, "params": {}},
    )
    response.raise_for_status()
    payload = response.json()
    run_id = str(payload["run_id"])
    console.print(
        Panel.fit(
            f"[green]已创建供应链图谱批次[/green]\nrun_id: [bold]{run_id}[/bold]\nstatus: {payload.get('status')}",
            title="Supply Graph Batch",
        ),
    )
    return run_id


def status_counts(tasks: list[dict[str, Any]]) -> dict[str, int]:
    """Count task statuses."""
    counts: dict[str, int] = {}
    for task in tasks:
        status = str(task.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def render_detail(detail: dict[str, Any]) -> None:
    """Render a run detail snapshot."""
    run = detail.get("run", {})
    tasks = detail.get("tasks", [])
    counts = status_counts(tasks)
    table = Table(title=f"Run {run.get('id') or run.get('run_id') or ''}")
    table.add_column("字段", style="cyan")
    table.add_column("值", style="white")
    table.add_row("status", str(run.get("status")))
    table.add_row("universe", str(run.get("universe")))
    table.add_row("total", str(run.get("total")))
    table.add_row("completed", str(run.get("completed")))
    table.add_row("failed", str(run.get("failed")))
    table.add_row("queued/running/retrying", f"{counts.get('queued', 0)}/{counts.get('running', 0)}/{counts.get('retrying', 0)}")
    table.add_row("paused_quota", str(counts.get("paused_quota", 0)))
    console.clear()
    console.print(table)


def watch_run(client: httpx.Client, options: BatchOptions, run_id: str) -> None:
    """Poll and render the run detail until completion."""
    terminal_statuses = {"done", "failed", "paused", "paused_quota"}
    while True:
        response = client.get(f"{options.api_base}/api/v1/supply-graph/runs/{run_id}")
        response.raise_for_status()
        detail = response.json()
        render_detail(detail)
        status = str(detail.get("run", {}).get("status") or "")
        if status in terminal_statuses:
            return
        time.sleep(options.interval)


def main() -> int:
    """Run the CLI."""
    options = parse_args()
    try:
        with httpx.Client(timeout=options.timeout) as client:
            run_id = create_run(client, options)
            if options.watch:
                watch_run(client, options, run_id)
    except httpx.HTTPError as exc:
        console.print(f"[red]请求失败：{exc}[/red]")
        return 1
    except KeyError as exc:
        console.print(f"[red]接口返回缺少字段：{exc}[/red]")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
