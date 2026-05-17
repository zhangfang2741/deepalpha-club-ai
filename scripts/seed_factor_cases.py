"""拉真实 K 线 + 计算因子快照，更新 factor_skills 表的 snapshot_factor_jsonb。

用法::

    uv run python scripts/seed_factor_cases.py --dry-run   # 只打印，不写入
    uv run python scripts/seed_factor_cases.py --with-data  # 真实计算 + 写入
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

CASE_CONFIGS = [
    {"symbol": "NVDA", "lookback": 60},
    {"symbol": "600519", "lookback": 20},
    {"symbol": "510300", "lookback": 20},
    {"symbol": "TSLA", "lookback": 20},
    {"symbol": "601318", "lookback": 14},
    {"symbol": "300750", "lookback": 20},
]


def compute_snapshot(symbol: str, lookback: int) -> dict:
    """用 FMP API 拉 K 线，计算因子 + 信号点，返回 snapshot dict。

    Args:
        symbol: 股票代码。
        lookback: 动量回看天数。

    Returns:
        包含 factor/signals/metrics 的 snapshot 字典。
    """
    import httpx

    fmp_key = os.environ.get("FMP_API_KEY", "")
    url = "https://financialmodelingprep.com/stable/historical-price-eod/full"
    resp = httpx.get(
        url,
        params={"symbol": symbol, "from": "2023-01-01", "to": "2025-05-16", "apikey": fmp_key},
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json()
    records = raw if isinstance(raw, list) else raw.get("historical", [])
    records.sort(key=lambda r: r["date"])

    closes = [r["close"] for r in records]
    n = len(closes)
    factor_raw = [None] * n
    for i in range(lookback + 5, n):
        factor_raw[i] = closes[i - 5] / closes[i - lookback - 5] - 1.0

    valid = [v for v in factor_raw if v is not None]
    if not valid:
        return {"factor": [], "signals": [], "metrics": {}}
    mean = sum(valid) / len(valid)
    std = (sum((v - mean) ** 2 for v in valid) / len(valid)) ** 0.5 or 1.0
    factor_z = [None if v is None else round((v - mean) / std, 4) for v in factor_raw]

    # 找信号点（|z| >= 1.5 的局部极值，至多 4 个）
    signal_idxs, in_zone, peak_idx, peak_abs = [], False, -1, 0.0
    for i, z in enumerate(factor_z):
        if z is None:
            continue
        if abs(z) >= 1.5:
            if not in_zone or abs(z) > peak_abs:
                peak_idx, peak_abs = i, abs(z)
            in_zone = True
        else:
            if in_zone and peak_idx >= 0:
                signal_idxs.append(peak_idx)
                peak_idx, peak_abs = -1, 0.0
            in_zone = False
    if in_zone and peak_idx >= 0:
        signal_idxs.append(peak_idx)
    signal_idxs = sorted(signal_idxs[:4])

    signals = [
        {"date": records[i]["date"], "z": factor_z[i], "close": records[i]["close"]}
        for i in signal_idxs
    ]
    factor_series = [
        {"time": records[i]["date"], "value": factor_z[i]}
        for i in range(n)
        if factor_z[i] is not None
    ]
    last_z = factor_series[-1]["value"] if factor_series else 0.0
    trigger_count = sum(1 for z in factor_z if z is not None and abs(z) >= 1.0)

    return {
        "factor": factor_series,
        "signals": signals,
        "metrics": {
            "current_z": round(last_z, 2),
            "data_days": n,
            "trigger_count": trigger_count,
        },
    }


def main() -> None:
    """解析命令行参数，遍历 CASE_CONFIGS 计算并写入快照。"""
    import sqlalchemy as sa
    from sqlmodel import Session

    from app.db.session import sync_engine

    dry_run = "--dry-run" in sys.argv
    with_data = "--with-data" in sys.argv

    if not dry_run and not with_data:
        print("用法: --dry-run 或 --with-data")
        sys.exit(1)

    for cfg in CASE_CONFIGS:
        symbol = cfg["symbol"]
        print(f"处理 {symbol}...")
        if with_data:
            snapshot = compute_snapshot(symbol, cfg["lookback"])
        else:
            print("  [dry-run] snapshot={}")
            continue

        with Session(sync_engine) as session:
            session.execute(
                sa.text(
                    "UPDATE factor_skills SET snapshot_factor_jsonb = :snap "
                    "WHERE default_symbol = :sym AND owner_id IS NULL"
                ),
                {"snap": json.dumps(snapshot), "sym": symbol},
            )
            session.commit()
        factor_count = len(snapshot.get("factor", []))
        print(f"  {symbol} snapshot 写入成功（{factor_count} 点）")

    print("Done.")


if __name__ == "__main__":
    main()
