"""子进程入口：从 stdin 读 JSON {"code", "price", "symbol", "start_date", "end_date"}
执行因子代码（compute 函数），stdout 写 {"records": [...], "output_type": str}
"""
from __future__ import annotations

import json
import re
import sys
import traceback

import math
import numpy as np
import pandas as pd

_ALLOWED_NS = {
    "math": math, "np": np, "numpy": np, "pd": pd, "pandas": pd,
    # ast_check.py 已在 AST 层拦截 __import__/getattr/open 等危险调用，
    # 此处放开完整 __builtins__ 以兼容 pandas/numpy C 代码内部依赖
    "__builtins__": __builtins__,
}


_REDUNDANT_IMPORT = re.compile(
    r"^[ \t]*(?:from\s+(?:numpy|pandas|math)(?:\.\w+)?\s+import\s+.+|"
    r"import\s+(?:numpy|pandas|math)(?:\s+as\s+\w+)?)\s*$",
    re.MULTILINE,
)


def _strip_redundant_imports(code: str) -> str:
    """剥掉顶层冗余的 numpy/pandas/math import 行（沙箱已注入 np/pd/math）"""
    return _REDUNDANT_IMPORT.sub("", code)


def _run(payload: dict) -> dict:
    code = _strip_redundant_imports(payload["code"])
    price_records = payload["price"]
    symbol = payload["symbol"]
    news_records = payload.get("news", [])
    financials = payload.get("financials", {})

    ns = dict(_ALLOWED_NS)
    ns["prices"] = price_records
    ns["news"] = news_records
    # 财务数据 dict（含 income_statement/balance_sheet/cash_flow/key_metrics/analyst_estimates/dcf/dividends）
    ns["financials"] = financials
    # analyst_estimates 和 dcf/dividends 也作为顶层变量方便访问
    if isinstance(financials, dict):
        ns["analyst_estimates"] = financials.get("analyst_estimates", [])
        ns["dcf"] = financials.get("dcf", [])
        ns["dividends"] = financials.get("dividends", [])
        ns["income_statement"] = financials.get("income_statement", [])
        ns["balance_sheet"] = financials.get("balance_sheet", [])
        ns["cash_flow"] = financials.get("cash_flow", [])
        ns["key_metrics"] = financials.get("key_metrics", [])
        ns["earnings"] = financials.get("earnings", [])
        ns["profile"] = financials.get("profile", {})
    exec(code, ns)  # noqa: S102

    if "compute" not in ns:
        raise RuntimeError("因子代码必须定义 compute(prices, symbol) 函数")

    result = ns["compute"](price_records, symbol)

    if not isinstance(result, list):
        raise TypeError(f"compute() 必须返回 list，实际返回 {type(result).__name__}")

    return {"records": result, "output_type": "factor"}


if __name__ == "__main__":
    try:
        payload = json.loads(sys.stdin.read())
        output = _run(payload)
        sys.stdout.write(json.dumps(output))
    except Exception as exc:
        sys.stderr.write(f"{exc}\n{traceback.format_exc()}")
        sys.exit(1)
