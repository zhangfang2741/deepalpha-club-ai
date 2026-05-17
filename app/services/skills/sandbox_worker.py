"""
子进程入口：从 stdin 读 JSON {"code", "price", "symbol", "start_date", "end_date"}
执行因子代码（compute 函数），stdout 写 {"records": [...], "output_type": str}
"""
from __future__ import annotations

import json
import sys
import traceback

import math
import numpy as np
import pandas as pd

_ALLOWED_NS = {
    "abs": abs, "len": len, "range": range, "enumerate": enumerate,
    "zip": zip, "min": min, "max": max, "sum": sum, "sorted": sorted,
    "reversed": reversed, "list": list, "dict": dict, "tuple": tuple,
    "set": set, "float": float, "int": int, "str": str, "bool": bool,
    "type": type, "isinstance": isinstance, "round": round, "pow": pow,
    "None": None, "True": True, "False": False,
    "math": math, "np": np, "numpy": np, "pd": pd, "pandas": pd,
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
    "__builtins__": {},
}


def _run(payload: dict) -> dict:
    code = payload["code"]
    price_records = payload["price"]
    symbol = payload["symbol"]
    start_date = payload["start_date"]
    end_date = payload["end_date"]

    ns = dict(_ALLOWED_NS)
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
