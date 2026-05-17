"""执行编排：AST 检查 → subprocess 沙箱 → 信号点 → 标准化"""
from __future__ import annotations

import math

from app.services.skills.ast_check import check_code_safety
from app.services.skills.errors import SkillDataError
from app.services.skills.sandbox import run_in_subprocess


async def compute_factor_snapshot(
    code: str,
    price_records: list[dict],
    symbol: str,
    start_date: str,
    end_date: str,
) -> dict:
    """执行 skill，返回 {factor, signals, metrics} 快照 dict。"""
    check_code_safety(code)

    raw_result, output_type = await run_in_subprocess(
        code, price_records, symbol, start_date, end_date, timeout=30.0,
    )

    if not raw_result:
        raise SkillDataError("因子计算返回空结果")

    # 提取 factor series
    factor_series = []
    for r in raw_result:
        t = r.get("time") or r.get("date", "")
        v = r.get("value")
        if t and v is not None and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            factor_series.append({"time": t, "value": float(v)})

    if len(factor_series) < 10:
        raise SkillDataError(f"有效数据点不足（{len(factor_series)}），需要至少 10 个")

    # z-score 标准化
    values = [f["value"] for f in factor_series]
    mean = sum(values) / len(values)
    std = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5 or 1.0
    factor_z = [{"time": f["time"], "value": round((f["value"] - mean) / std, 4)}
                for f in factor_series]

    # 找信号点（|z| >= 1.5 的局部极值，取 top 4）
    signal_idxs, in_zone, peak_idx, peak_abs = [], False, -1, 0.0
    for i, f in enumerate(factor_z):
        z = abs(f["value"])
        if z >= 1.5:
            if not in_zone or z > peak_abs:
                peak_idx, peak_abs = i, z
            in_zone = True
        else:
            if in_zone and peak_idx >= 0:
                signal_idxs.append(peak_idx)
                peak_idx, peak_abs = -1, 0.0
            in_zone = False
    if in_zone and peak_idx >= 0:
        signal_idxs.append(peak_idx)

    top4 = sorted(signal_idxs, key=lambda i: -abs(factor_z[i]["value"]))[:4]
    sorted_top4 = sorted(top4)  # 按时间排序

    # 构建 close 价格映射
    date_to_close: dict[str, float] = {
        r.get("date", r.get("time", "")): float(r.get("close", r.get("value", 0)))
        for r in price_records
    }

    signals = [
        {
            "date": factor_z[i]["time"],
            "z": round(factor_z[i]["value"], 2),
            "close": date_to_close.get(factor_z[i]["time"], 0.0),
        }
        for i in sorted_top4
    ]

    last_z = factor_z[-1]["value"]
    peak_z = max(abs(f["value"]) for f in factor_z)
    trigger_count = sum(1 for f in factor_z if abs(f["value"]) >= 1.0)

    return {
        "factor": factor_z,
        "signals": signals,
        "metrics": {
            "current_z": round(last_z, 2),
            "peak_z": round(peak_z, 2),
            "data_days": len(factor_series),
            "trigger_count": trigger_count,
        },
    }
