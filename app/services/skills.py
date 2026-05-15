"""Skill factor explorer service: streaming code generation, K-line fetch, sandbox execution."""

import ast
import asyncio
import datetime as _datetime
import math as _math
import re
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator

import numpy as np
import pandas as pd
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from redis.asyncio import Redis

from app.cache.operations import get_json, set_json
from app.core.logging import logger
from app.schemas.skills import FactorPoint, KlineBar
from app.services.llm.registry import llm_registry

_executor = ThreadPoolExecutor(max_workers=4)

# ─── System Prompt ────────────────────────────────────────────────────────────

SKILL_SYSTEM_PROMPT = """你是 DeepAlpha 因子探索助手。你的职责是根据用户描述的量化分析思路，生成可执行的因子计算规则，并向用户用简洁非技术语言解释结果。

## 生成规则
必须生成一个类，满足以下结构：

```python
import pandas as pd
import numpy as np

class MySkill(BaseSkill):
    output_type = "factor"  # factor | signal | risk | report

    def run(self, ctx):
        prices = ctx.get_price()
        # prices 是 pandas DataFrame，列：date(str), symbol(str), close, open, high, low, volume
        # 在这里实现因子计算逻辑...
        result = pd.DataFrame({
            'date': prices['date'],
            'value': factor_values   # 因子分数，float
        })
        return SkillResult(data=result)
```

## 可用库
- `import pandas as pd` / `import numpy as np`
- `import math` / `import datetime`
- 禁止：os, sys, subprocess, requests, socket, exec, eval, open, __import__

## 对用户的回复要求
1. 先用1-3句中文说明"因子逻辑"（例如："此因子衡量过去90天价格涨幅，高分代表强动量"）
2. 然后附上完整代码块
3. 绝对不提"Python"、"代码"、"函数"、"class"等技术词汇，改用"因子逻辑"、"计算规则"
4. 迭代修改时重新生成完整代码（不省略）

## 数据说明
- ctx.get_price() 返回单只股票的历史价格，date 列为字符串 YYYY-MM-DD 格式
- result 的 value 列建议做标准化（z-score）或归一化（0~1），方便图表展示
"""

# ─── 代码生成（流式）─────────────────────────────────────────────────────────

def _build_lc_messages(messages: list) -> list:
    lc = [SystemMessage(content=SKILL_SYSTEM_PROMPT)]
    for msg in messages:
        if msg.role == "user":
            lc.append(HumanMessage(content=msg.content))
        else:
            lc.append(AIMessage(content=msg.content))
    return lc


async def generate_skill_stream(
    messages: list,
    model_name: str,
) -> AsyncGenerator[str, None]:
    """Stream Skill code generation, yielding text tokens incrementally."""
    lc_messages = _build_lc_messages(messages)
    try:
        llm = llm_registry.get(model_name)
    except ValueError:
        logger.warning("skill_model_not_found_using_default", requested=model_name)
        llm = llm_registry.LLMS[0]["llm"]

    logger.info("skill_generate_stream_start", model=model_name, turns=len(messages))
    async for chunk in llm.astream(lc_messages):
        text = chunk.content if isinstance(chunk.content, str) else ""
        if not text and isinstance(chunk.content, list):
            text = "".join(
                c.get("text", "") for c in chunk.content
                if isinstance(c, dict) and c.get("type") == "text"
            )
        if text:
            yield text


# ─── AST 安全检查 ──────────────────────────────────────────────────────────

_FORBIDDEN_IMPORTS = {
    "os", "sys", "subprocess", "requests", "socket",
    "shutil", "glob", "pathlib", "tempfile", "importlib",
    "ctypes", "multiprocessing", "threading",
}
_FORBIDDEN_CALLS = {"exec", "eval", "open", "compile", "__import__"}


def _check_ast_safety(code: str) -> None:
    """Statically analyse the AST and reject dangerous imports or function calls."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"语法错误：{e}") from e

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                base = alias.name.split(".")[0]
                if base in _FORBIDDEN_IMPORTS:
                    raise ValueError(f"禁止导入模块：{base}")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALLS:
                raise ValueError(f"禁止调用函数：{node.func.id}")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__") and node.attr not in (
                "__init__", "__str__", "__repr__", "__len__", "__iter__",
                "__next__", "__getitem__", "__setitem__",
            ):
                raise ValueError(f"禁止访问属性：{node.attr}")


# ─── Skill 沙箱执行 ────────────────────────────────────────────────────────

class _SkillContext:
    def __init__(self, price_df: pd.DataFrame, symbol: str, start_date: str, end_date: str):
        self._price = price_df
        self.symbols = [symbol]
        self.start_date = start_date
        self.end_date = end_date
        self.params: dict = {}

    def get_price(self) -> pd.DataFrame:
        return self._price.copy()

    def get_income(self) -> pd.DataFrame:
        return pd.DataFrame()

    def get_balance(self) -> pd.DataFrame:
        return pd.DataFrame()

    def get_cashflow(self) -> pd.DataFrame:
        return pd.DataFrame()


class _SkillResult:
    def __init__(self, data: pd.DataFrame, output_type: str = "factor"):
        self.data = data
        self.output_type = output_type


_ALLOWED_IMPORT_MODULES = frozenset({
    "pandas", "numpy", "math", "datetime", "statistics",
    "itertools", "functools", "collections", "typing",
})

import builtins as _builtins  # noqa: E402

_original_import = _builtins.__import__


def _restricted_import(name: str, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
    base = name.split(".")[0]
    if base not in _ALLOWED_IMPORT_MODULES:
        raise ImportError(f"禁止导入模块：{base}")
    return _original_import(name, globals, locals, fromlist, level)


_SAFE_BUILTINS = {
    "len": len, "range": range, "list": list, "dict": dict, "tuple": tuple,
    "set": set, "str": str, "int": int, "float": float, "bool": bool,
    "zip": zip, "enumerate": enumerate, "sorted": sorted, "reversed": reversed,
    "map": map, "filter": filter, "any": any, "all": all,
    "min": min, "max": max, "sum": sum, "abs": abs, "round": round,
    "print": print, "isinstance": isinstance, "issubclass": issubclass,
    "hasattr": hasattr, "getattr": getattr, "setattr": setattr,
    "None": None, "True": True, "False": False,
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
    "AttributeError": AttributeError, "KeyError": KeyError, "IndexError": IndexError,
    "NotImplementedError": NotImplementedError,
    "__import__": _restricted_import,
    "__build_class__": __build_class__,
}


def _run_in_sandbox(
    code: str,
    price_df: pd.DataFrame,
    symbol: str,
    start_date: str,
    end_date: str,
) -> tuple[list[dict], str]:
    namespace: dict = {
        "__builtins__": _SAFE_BUILTINS,
        "__name__": "__skill__",
        "pd": pd,
        "pandas": pd,
        "np": np,
        "numpy": np,
        "math": _math,
        "datetime": _datetime,
        "BaseSkill": object,
        "SkillContext": _SkillContext,
        "SkillResult": _SkillResult,
    }

    exec(compile(code, "<skill>", "exec"), namespace)  # noqa: S102

    skill_class = None
    reserved = {"SkillContext", "SkillResult", "BaseSkill"}
    for name, val in namespace.items():
        if isinstance(val, type) and val is not object and name not in reserved:
            skill_class = val
            break

    if skill_class is None:
        raise ValueError("未找到 Skill 类定义")

    ctx = _SkillContext(price_df, symbol, start_date, end_date)
    result = skill_class().run(ctx)

    if not hasattr(result, "data"):
        raise ValueError("run() 必须返回 SkillResult(data=...)")

    output_type = getattr(result, "output_type", "factor")
    df = result.data
    if isinstance(df, pd.DataFrame):
        records = df.to_dict("records")
    elif isinstance(df, list):
        records = df
    else:
        raise ValueError("SkillResult.data 必须是 DataFrame 或 list")

    return records, str(output_type)


def _normalize_to_factor_points(records: list[dict]) -> list[FactorPoint]:
    if not records:
        return []

    sample = records[0]
    date_col = next((k for k in sample if k in ("date", "time", "日期", "Date")), None)
    if not date_col:
        raise ValueError("结果缺少日期列（date / time）")

    value_col = next(
        (
            k for k in sample
            if k not in (date_col, "symbol", "股票代码", "Symbol")
            and isinstance(sample.get(k), (int, float))
            and not (isinstance(sample.get(k), float) and _math.isnan(sample[k]))
        ),
        None,
    )
    if not value_col:
        raise ValueError("结果缺少数值列（value / factor / score 等）")

    points = []
    for r in records:
        t = str(r[date_col])
        v = r.get(value_col)
        if v is None or (isinstance(v, float) and (_math.isnan(v) or _math.isinf(v))):
            continue
        points.append(FactorPoint(time=t, value=float(v)))

    return sorted(points, key=lambda p: p.time)


async def execute_skill(
    code: str,
    price_df: pd.DataFrame,
    symbol: str,
    start_date: str,
    end_date: str,
) -> tuple[list[FactorPoint], str]:
    """Run AST safety check then execute the Skill in a sandbox, returning factor points and output_type."""
    _check_ast_safety(code)

    loop = asyncio.get_event_loop()
    try:
        records, output_type = await asyncio.wait_for(
            loop.run_in_executor(
                _executor, _run_in_sandbox, code, price_df, symbol, start_date, end_date
            ),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        raise ValueError("Skill 执行超时（30秒），请简化计算逻辑")

    points = _normalize_to_factor_points(records)
    return points, output_type


# ─── K 线数据获取 + 缓存 ──────────────────────────────────────────────────

_KLINE_TTL = 600  # 10 分钟


def _is_a_share(symbol: str) -> bool:
    clean = re.sub(r"^(SH|SZ|sh|sz)", "", symbol).strip()
    return bool(re.match(r"^\d{6}$", clean))


def _clean_symbol(symbol: str) -> str:
    return re.sub(r"^(SH|SZ|sh|sz)", "", symbol).strip()


def _fetch_a_share_kline(symbol: str, start_date: str, end_date: str, freq: str) -> pd.DataFrame:
    import akshare as ak  # noqa: PLC0415

    period = "daily" if freq == "daily" else "weekly"
    start_fmt = start_date.replace("-", "")
    end_fmt = end_date.replace("-", "")
    df = ak.stock_zh_a_hist(
        symbol=_clean_symbol(symbol),
        period=period,
        start_date=start_fmt,
        end_date=end_fmt,
        adjust="qfq",
    )
    col_map = {
        "日期": "date", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low", "成交量": "volume",
    }
    df = df.rename(columns=col_map)
    df["date"] = df["date"].astype(str)
    df["symbol"] = symbol
    return df[["date", "symbol", "open", "high", "low", "close", "volume"]]


def _fetch_us_kline(symbol: str, start_date: str, end_date: str, freq: str) -> pd.DataFrame:
    import yfinance as yf  # noqa: PLC0415

    interval = "1d" if freq == "daily" else "1wk"
    ticker = yf.Ticker(symbol)
    hist = ticker.history(start=start_date, end=end_date, interval=interval)
    hist = hist.reset_index()
    hist["date"] = pd.to_datetime(hist["Date"]).dt.strftime("%Y-%m-%d")
    hist = hist.rename(columns={
        "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume",
    })
    hist["symbol"] = symbol
    return hist[["date", "symbol", "open", "high", "low", "close", "volume"]]


def _fetch_kline_sync(symbol: str, start_date: str, end_date: str, freq: str) -> pd.DataFrame:
    if _is_a_share(symbol):
        return _fetch_a_share_kline(symbol, start_date, end_date, freq)
    return _fetch_us_kline(symbol, start_date, end_date, freq)


def _df_to_kline_bars(df: pd.DataFrame) -> list[KlineBar]:
    bars = []
    for _, row in df.iterrows():
        try:
            bars.append(KlineBar(
                time=str(row["date"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            ))
        except (KeyError, ValueError):
            continue
    return bars


def _kline_cache_key(symbol: str, start_date: str, end_date: str, freq: str) -> str:
    return f"skill_kline:{symbol}:{start_date}:{end_date}:{freq}"


async def fetch_and_cache_kline(
    redis: Redis,
    symbol: str,
    start_date: str,
    end_date: str,
    freq: str,
) -> tuple[list[KlineBar], pd.DataFrame]:
    """Fetch K-line data (Redis-first), returning chart bars and a DataFrame for Skill execution."""
    cache_key = _kline_cache_key(symbol, start_date, end_date, freq)

    cached = await get_json(redis, cache_key)
    if cached and "records" in cached:
        records = cached["records"]
        df = pd.DataFrame(records)
        bars = _df_to_kline_bars(df)
        logger.info("skill_kline_cache_hit", symbol=symbol, key=cache_key)
        return bars, df

    logger.info("skill_kline_fetch_start", symbol=symbol, start=start_date, end=end_date)
    loop = asyncio.get_event_loop()
    try:
        df = await asyncio.wait_for(
            loop.run_in_executor(_executor, _fetch_kline_sync, symbol, start_date, end_date, freq),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        raise ValueError(f"K 线数据获取超时：{symbol}")

    if df.empty:
        raise ValueError(f"未获取到 {symbol} 的 K 线数据，请检查股票代码和日期范围")

    records = df.to_dict("records")
    await set_json(redis, cache_key, {"records": records}, expire=_KLINE_TTL)

    bars = _df_to_kline_bars(df)
    logger.info("skill_kline_fetched_and_cached", symbol=symbol, bars=len(bars))
    return bars, df


async def get_cached_price_df(
    redis: Redis,
    symbol: str,
    start_date: str,
    end_date: str,
    freq: str,
) -> pd.DataFrame | None:
    """Return the cached price DataFrame from Redis, or None when the cache is cold."""
    cache_key = _kline_cache_key(symbol, start_date, end_date, freq)
    cached = await get_json(redis, cache_key)
    if cached and "records" in cached:
        return pd.DataFrame(cached["records"])
    return None
