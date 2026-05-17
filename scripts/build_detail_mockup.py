"""拉取 NVDA 真实 K 线 + 算 60 日动量因子，注入到详情页 mockup HTML 中"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

FMP_API_KEY = os.environ["FMP_API_KEY"]
SYMBOL = "NVDA"
FROM_DATE = "2024-01-01"
TO_DATE = "2025-12-30"

# ─── 1. 拉 FMP 历史价 ─────────────────────────────────────────────
url = "https://financialmodelingprep.com/stable/historical-price-eod/full"
resp = httpx.get(
    url,
    params={"symbol": SYMBOL, "from": FROM_DATE, "to": TO_DATE, "apikey": FMP_API_KEY},
    timeout=30,
)
resp.raise_for_status()
payload = resp.json()

# FMP 可能返回 dict 包 historical 字段，也可能直接是 list
records = payload if isinstance(payload, list) else payload.get("historical", [])
if not records:
    raise SystemExit(f"FMP 未返回数据，原始响应：{json.dumps(payload)[:300]}")

# 升序排序
records.sort(key=lambda r: r["date"])

# ─── 2. 计算 60 日动量因子（跳过最近 5 日，z-score 标准化）────────
LOOKBACK = 60
SKIP = 5

closes = [r["close"] for r in records]
factor_raw: list[float | None] = [None] * len(closes)
for i in range(LOOKBACK + SKIP, len(closes)):
    base = closes[i - LOOKBACK - SKIP]
    end = closes[i - SKIP]
    factor_raw[i] = (end / base - 1.0) if base else None

valid = [v for v in factor_raw if v is not None]
mean = sum(valid) / len(valid)
var = sum((v - mean) ** 2 for v in valid) / len(valid)
std = var**0.5 or 1.0
factor_z = [None if v is None else (v - mean) / std for v in factor_raw]

# ─── 3. 找信号点（>+1.5σ 或 <-1.5σ 的局部极值）─────────────────
def find_signals(z_list: list[float | None], threshold: float = 1.5) -> list[int]:
    """返回穿越阈值的索引"""
    points: list[int] = []
    in_zone = False
    peak_idx = -1
    peak_abs = 0.0
    for i, z in enumerate(z_list):
        if z is None:
            continue
        if abs(z) >= threshold:
            if not in_zone or abs(z) > peak_abs:
                peak_idx = i
                peak_abs = abs(z)
            in_zone = True
        else:
            if in_zone and peak_idx >= 0:
                points.append(peak_idx)
                peak_idx = -1
                peak_abs = 0.0
            in_zone = False
    if in_zone and peak_idx >= 0:
        points.append(peak_idx)
    return points

signal_idxs = find_signals(factor_z, threshold=1.5)
# 至多取 4 个最显著的
signal_idxs.sort(key=lambda i: -abs(factor_z[i] or 0))
signal_idxs = sorted(signal_idxs[:4])

signals = [
    {"date": records[i]["date"], "z": round(factor_z[i] or 0, 2), "close": records[i]["close"]}
    for i in signal_idxs
]

# ─── 4. K 线 + 因子序列输出（lightweight-charts 格式）─────────────
kline_series = [
    {"time": r["date"], "open": r["open"], "high": r["high"], "low": r["low"], "close": r["close"]}
    for r in records
]
factor_series = [
    {"time": records[i]["date"], "value": round(factor_z[i] or 0, 4)}
    for i in range(len(records))
    if factor_z[i] is not None
]

# ─── 5. 指标卡数据 ───────────────────────────────────────────────
last_z = factor_series[-1]["value"]
peak_pos_idx = max(range(len(factor_z)), key=lambda i: factor_z[i] if factor_z[i] is not None else -999)
peak_z = factor_z[peak_pos_idx]
peak_date = records[peak_pos_idx]["date"]
trigger_count = sum(1 for z in factor_z if z is not None and abs(z) >= 1.0)

last_close = records[-1]["close"]
prev_close = records[-2]["close"] if len(records) > 1 else last_close
pct_change = (last_close / prev_close - 1) * 100

metrics = {
    "current_z": last_z,
    "peak_z": peak_z,
    "peak_date": peak_date,
    "trigger_count": trigger_count,
    "data_days": len(records),
    "last_close": last_close,
    "pct_change": pct_change,
    "first_date": records[0]["date"],
    "last_date": records[-1]["date"],
}

# ─── 6. 写出 JSON 数据文件 ───────────────────────────────────────
out = {
    "symbol": SYMBOL,
    "kline": kline_series,
    "factor": factor_series,
    "signals": signals,
    "metrics": metrics,
}

# 输出到视觉伴侣最新 session 目录
sessions = sorted((ROOT / ".superpowers" / "brainstorm").glob("*"), key=lambda p: p.stat().st_mtime)
if not sessions:
    raise SystemExit("找不到 .superpowers/brainstorm session 目录")
target_dir = sessions[-1] / "content"
target_dir.mkdir(parents=True, exist_ok=True)

(target_dir / "nvda_data.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
print(f"✔ 数据写入 {target_dir / 'nvda_data.json'}")
print(f"  K 线 {len(kline_series)} 条 · 因子 {len(factor_series)} 条 · 信号 {len(signals)} 个")
print(f"  当前 z = {last_z:+.2f}σ · 历史峰值 {peak_z:+.2f}σ ({peak_date}) · 触发 {trigger_count} 次")
for s in signals:
    print(f"  ⭐ {s['date']}  z={s['z']:+.2f}σ  close=${s['close']:.2f}")
