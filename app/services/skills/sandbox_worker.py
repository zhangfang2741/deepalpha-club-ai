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
    # 类型检查：确保 financial 各字段都是 list/dict，API 失败时可能返回 string
    ns["news"] = news_records if isinstance(news_records, list) else []
    if isinstance(financials, dict):
        ns["financials"] = financials
        ns["analyst_estimates"] = financials.get("analyst_estimates") if isinstance(financials.get("analyst_estimates"), list) else []
        ns["dcf"] = financials.get("dcf") if isinstance(financials.get("dcf"), list) else []
        ns["dividends"] = financials.get("dividends") if isinstance(financials.get("dividends"), list) else []
        ns["income_statement"] = financials.get("income_statement") if isinstance(financials.get("income_statement"), list) else []
        ns["balance_sheet"] = financials.get("balance_sheet") if isinstance(financials.get("balance_sheet"), list) else []
        ns["cash_flow"] = financials.get("cash_flow") if isinstance(financials.get("cash_flow"), list) else []
        ns["key_metrics"] = financials.get("key_metrics") if isinstance(financials.get("key_metrics"), list) else []
        ns["earnings"] = financials.get("earnings") if isinstance(financials.get("earnings"), list) else []
        ns["profile"] = financials.get("profile") if isinstance(financials.get("profile"), dict) else {}
        # employees 字段是单一当前值，不是时间序列
        ns["current_employees"] = ns["profile"].get("employees") if isinstance(ns["profile"], dict) else None
        # employee_count 是时间序列（年度），可用于计算员工增长因子
        ns["employee_count"] = financials.get("employee_count") if isinstance(financials.get("employee_count"), list) else []
    else:
        ns["financials"] = {}
        for k in ["analyst_estimates", "dcf", "dividends", "income_statement",
                  "balance_sheet", "cash_flow", "key_metrics", "earnings",
                  "profile", "employee_count"]:
            ns[k] = [] if k != "profile" else {}
        ns["current_employees"] = None
    exec(code, ns)  # noqa: S102

    if "compute" not in ns:
        raise RuntimeError("因子代码必须定义 compute(prices, symbol) 函数")

    try:
        result = ns["compute"](price_records, symbol)
    except Exception as exc:
        import sys as _sys
        _sys.stderr.write(f"[sandbox] compute 错误: {exc}\n")
        raise

    if not isinstance(result, list):
        raise TypeError(f"compute() 必须返回 list，实际返回 {type(result).__name__}")

    # 日志输出，方便排查（不影响主流程）
    import sys as _sys
    _sys.stderr.write(f"[sandbox] compute returned {len(result)} records\n")
    if result:
        _sys.stderr.write(f"[sandbox] first record: {result[0]}\n")
    return {"records": result, "output_type": "factor"}


if __name__ == "__main__":
    try:
        payload = json.loads(sys.stdin.read())
        output = _run(payload)
        sys.stdout.write(json.dumps(output))
    except Exception as exc:
        sys.stderr.write(f"{exc}\n{traceback.format_exc()}")
        sys.exit(1)
