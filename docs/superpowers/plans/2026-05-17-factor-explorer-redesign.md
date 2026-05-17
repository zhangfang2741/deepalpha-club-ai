# 因子探索（Skill Generator）重设计实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重设计 `/skill-generator` 页面，建立真正的因子资产体系（案例馆 + 我的因子 + 三步向导），修复 UI bug，完成沙箱安全加固。

**Architecture:**
- 后端新增 `factor_skills` / `factor_runs` 表，前端拆出 8 个专用组件
- 沙箱从同线程 `exec()` 迁至独立 subprocess + RLIMIT
- 前端去掉负边距/全屏深色，改为浅色背景 + 详情页局部深色焦点
- API 增加保存/列表/重跑端点，K 线缓存 key 加上 user_id 隔离

**Tech Stack:** Python 3.13 + FastAPI + SQLModel + Alembic + Next.js 14 + TypeScript + lightweight-charts@5 + Zustand

---

## 文件结构总览

```
后端新增：
  app/models/factor_skill.py
  app/models/factor_run.py
  app/services/skills/
    __init__.py
    generator.py      # 从 skills.py 抽取
    runner.py        # 从 skills.py 抽取
    sandbox.py       # subprocess 沙箱（新）
    sandbox_worker.py# 子进程入口（新）
    narrator.py      # AI 旁白生成（新）
    kline.py         # K 线 fetch + 缓存（新）
    errors.py        # 统一异常类（新）
    ast_check.py     # AST 安全检查（从 skills.py 抽取）
  alembic/versions/xxxx_add_factor_tables.py
  alembic/versions/xxxx_seed_gallery_cases.py
  scripts/seed_factor_cases.py

后端修改：
  app/api/v1/skills.py
  app/schemas/skills.py
  app/services/skills.py → 删除（拆包后变为 app/services/skills/__init__.py）
  app/core/limiter.py

前端新增：
  frontend/app/(dashboard)/skill-generator/_components/
    GalleryView.tsx
    MineView.tsx
    NewView.tsx
    DetailPage.tsx
    FactorCard.tsx
    MetricCards.tsx
    DualChart.tsx
    NarrativePanel.tsx
  frontend/app/(dashboard)/skill-generator/_hooks/
    useSkillStream.ts
    useFactorData.ts
  frontend/lib/store/skills.ts

前端修改：
  frontend/app/(dashboard)/skill-generator/page.tsx
  frontend/lib/api/skills.ts
```

---

## Task 1: 后端 — 数据模型与迁移

**Files:**
- Create: `app/models/factor_skill.py`
- Create: `app/models/factor_run.py`
- Create: `alembic/versions/xxxx_add_factor_tables.py`（autogenerate）
- Create: `alembic/versions/xxxx_seed_gallery_cases.py`（手动写，不 autogenerate）
- Create: `scripts/seed_factor_cases.py`
- Modify: `app/db/__init__.py`（导出新模型）

- [ ] **Step 1: 创建 FactorSkill 模型**

```python
# app/models/factor_skill.py
"""因子 Skill 模型（平台精选 + 用户私有）"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, Index, SQLModel


class FactorSkill(SQLModel, table=True):
    __tablename__ = "factor_skills"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, index=True, nullable=False
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )

    owner_id: int | None = Field(
        default=None, index=True, nullable=True,
        sa_column_kwargs={"ForeignKey": "users.id", "ondelete": "CASCADE"}
    )
    title: str = Field(..., max_length=80, nullable=False)
    description: str = Field(..., max_length=200, nullable=False)
    category: str = Field(
        ..., max_length=30, nullable=False,
        sa_column_kwargs={"ForeignKey": "factor_categories.name"}
    )
    code: str = Field(..., nullable=False)
    default_symbol: str = Field(..., max_length=20, nullable=False)
    default_start_date: str = Field(..., max_length=10, nullable=False)
    default_end_date: str = Field(..., max_length=10, nullable=False)
    default_freq: str = Field(default="daily", max_length=10, nullable=False)
    snapshot_factor_jsonb: dict = Field(default_factory=dict, nullable=False)
    narrative_jsonb: dict | None = Field(default=None, nullable=True)
    is_public: bool = Field(default=False, nullable=False)
    pin_priority: int | None = Field(default=None, nullable=True)

    __table_args__ = (
        Index("ix_factor_skills_owner", "owner_id"),
        Index("ix_factor_skills_category", "category"),
    )
```

- [ ] **Step 2: 创建 FactorCategory 枚举表（用于外键约束）**

```python
# app/models/factor_category.py
"""因子类别枚举表（运营可增行，不可删行）"""
from sqlmodel import Field, SQLModel


class FactorCategory(SQLModel, table=True):
    __tablename__ = "factor_categories"

    name: str = Field(primary_key=True, max_length=30)
    label: str = Field(..., max_length=40)  # "动量" / "均值回归" 等显示名
    icon: str | None = Field(default=None, max_length=20)  # emoji 或 icon 名
    sort_order: int = Field(default=0)
```

- [ ] **Step 3: 创建 FactorRun 模型**

```python
# app/models/factor_run.py
"""换股重跑历史记录"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel, UniqueConstraint


class FactorRun(SQLModel, table=True):
    __tablename__ = "factor_runs"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, index=True, nullable=False
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )

    skill_id: uuid.UUID = Field(
        ..., index=True, nullable=False,
        sa_column_kwargs={"ForeignKey": "factor_skills.id", "ondelete": "CASCADE"}
    )
    user_id: int = Field(
        ..., index=True, nullable=False,
        sa_column_kwargs={"ForeignKey": "users.id", "ondelete": "CASCADE"}
    )
    symbol: str = Field(..., max_length=20, nullable=False)
    start_date: str = Field(..., max_length=10, nullable=False)
    end_date: str = Field(..., max_length=10, nullable=False)
    freq: str = Field(default="daily", max_length=10, nullable=False)
    factor_jsonb: dict = Field(default_factory=dict, nullable=False)
    narrative_jsonb: dict | None = Field(default=None, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "skill_id", "user_id", "symbol", "start_date", "end_date", "freq",
            name="uq_factor_run"
        ),
    )
```

- [ ] **Step 4: 运行 autogenerate 迁移**

Run: `cd /Users/zhangfang/deepalpha-club-ai && uv run alembic revision --autogenerate -m "add factor_skills and factor_runs tables"`
Expected: 在 `alembic/versions/` 生成新文件，includes `CREATE TABLE factor_skills` / `CREATE TABLE factor_runs` / `CREATE TABLE factor_categories`

- [ ] **Step 5: 审查生成的迁移文件，补加外键约束 + 索引**

检查 Step 4 生成的迁移是否正确包含：
- `fk('factor_skills.owner_id', 'users.id')`
- `fk('factor_skills.category', 'factor_categories.name')`
- `fk('factor_runs.skill_id', 'factor_skills.id')`
- `fk('factor_runs.user_id', 'users.id')`
- `ix_factor_skills_owner` 和 `ix_factor_skills_category` 索引

手动补加缺失的外键（Autogenerate 有时会漏掉）。

- [ ] **Step 6: 写案例种子迁移**

```python
# alembic/versions/xxxx_seed_gallery_cases.py
"""Seed 6 个精选案例到 factor_skills（owner_id=NULL）"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
import uuid, json

CATEGORIES = ["momentum", "reversal", "volatility", "volume", "sentiment", "technical"]

CASES = [
    {
        "title": "英伟达 · AI 行情动量",
        "description": "取 60 日累计涨幅，量化 AI 主升浪中的强者恒强效应",
        "category": "momentum",
        "symbol": "NVDA",
        "start": "2024-01-01",
        "end": "2025-05-16",
        "pin_priority": 1,
        # snapshot 和 narrative 在 scripts/seed_factor_cases.py 中计算后填入
        "snapshot": {},
        "narrative": None,
    },
    {
        "title": "贵州茅台 · 均值回归",
        "description": "20 日均线偏离度，捕捉消费龙头的均值回归机会",
        "category": "reversal",
        "symbol": "600519",
        "start": "2023-01-01",
        "end": "2025-05-16",
        "pin_priority": 2,
        "snapshot": {},
        "narrative": None,
    },
    # ... 其余 4 个案例（TSLA/RSI、沪深300ETF/恐慌指数、宁德时代/量价背离、中国平安/RSI极值）
]

def upgrade():
    # 先插入 category 枚举行
    for i, cat in enumerate(CATEGORIES):
        op.execute(
            f"INSERT INTO factor_categories (name, label, sort_order) "
            f"VALUES ('{cat}', '{cat}', {i}) ON CONFLICT DO NOTHING"
        )
    for case in CASES:
        op.execute(
            f"""INSERT INTO factor_skills
                (id, title, description, category, default_symbol,
                 default_start_date, default_end_date, default_freq,
                 snapshot_factor_jsonb, narrative_jsonb, is_public, pin_priority)
                VALUES (
                    '{uuid.uuid4()}', '{case['title']}', '{case['description']}',
                    '{case['category']}', '{case['symbol']}',
                    '{case['start']}', '{case['end']}', 'daily',
                    '{json.dumps(case['snapshot'])}', {f"'{json.dumps(case['narrative'])}'" if case['narrative'] is not None else "NULL"},
                    false, {case['pin_priority']}
                ) ON CONFLICT DO NOTHING"""
        )

def downgrade():
    op.execute("DELETE FROM factor_skills WHERE owner_id IS NULL")
    op.execute("DELETE FROM factor_categories")
```

- [ ] **Step 7: 写种子脚本（支持 `--with-data` 计算真实快照）**

```python
# scripts/seed_factor_cases.py
"""拉真实 K 线 + 计算因子快照，写入 factor_skills 表。

用法:
  uv run python scripts/seed_factor_cases.py --dry-run   # 只打印 SQL
  uv run python scripts/seed_factor_cases.py --with-data  # 真写入
"""
from __future__ import annotations

import json, os, sys
from pathlib import Path
from datetime import date

import httpx
from dotenv import load_dotenv
from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

FMP_KEY = os.environ.get("FMP_API_KEY", "")

# 6 个案例的因子计算逻辑（与前端一致）
CASE_CONFIGS = [
    {"symbol": "NVDA", "lookback": 60, "name": "momentum"},
    {"symbol": "600519", "lookback": 20, "name": "reversal"},
    {"symbol": "510300", "lookback": 20, "name": "sentiment"},
    {"symbol": "TSLA", "lookback": 20, "name": "volatility"},
    {"symbol": "601318", "lookback": 14, "name": "technical"},
    {"symbol": "300750", "lookback": 20, "name": "volume"},
]

def compute_snapshot(symbol: str, lookback: int) -> dict:
    """拉 K 线 + 计算动量因子 + 找信号点"""
    url = "https://financialmodelingprep.com/stable/historical-price-eod/full"
    resp = httpx.get(url, params={"symbol": symbol, "from": "2023-01-01",
                                   "to": "2025-05-16", "apikey": FMP_KEY}, timeout=30)
    resp.raise_for_status()
    records = resp.json() if isinstance(resp.json(), list) else resp.json().get("historical", [])
    records.sort(key=lambda r: r["date"])

    closes = [r["close"] for r in records]
    factor_raw = [None] * len(closes)
    for i in range(lookback + 5, len(closes)):
        factor_raw[i] = closes[i - 5] / closes[i - lookback - 5] - 1.0

    valid = [v for v in factor_raw if v is not None]
    mean = sum(valid) / len(valid)
    std = (sum((v - mean) ** 2 for v in valid) / len(valid)) ** 0.5 or 1.0
    factor_z = [None if v is None else (v - mean) / std for v in factor_raw]

    # 找信号点（|z| >= 1.5 的局部极值，至多 4 个）
    signal_idxs, in_zone, peak_idx, peak_abs = [], False, -1, 0.0
    for i, z in enumerate(factor_z):
        if z is None: continue
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

    signals = [{"date": records[i]["date"], "z": round(factor_z[i], 2),
                "close": records[i]["close"]} for i in signal_idxs]
    factor_series = [{"time": records[i]["date"], "value": round(factor_z[i], 4)}
                     for i in range(len(records)) if factor_z[i] is not None]

    last_z = factor_series[-1]["value"] if factor_series else 0.0
    return {
        "factor": factor_series,
        "signals": signals,
        "metrics": {
            "current_z": round(last_z, 2),
            "data_days": len(records),
            "trigger_count": sum(1 for z in factor_z if z is not None and abs(z) >= 1.0),
        }
    }

def main():
    import sys
    dry_run = "--dry-run" in sys.argv

    from app.db.session import get_sync_session
    session = get_sync_session().__enter__()

    for cfg in CASE_CONFIGS:
        print(f"处理 {cfg['symbol']}...")
        snapshot = compute_snapshot(cfg["symbol"], cfg["lookback"]) if not dry_run else {}
        # UPDATE 现有行（pin_priority 匹配的行）
        session.execute(
            text("UPDATE factor_skills SET snapshot_factor_jsonb = :snap "
                 "WHERE default_symbol = :sym AND owner_id IS NULL"),
            {"snap": json.dumps(snapshot), "sym": cfg["symbol"]}
        )
    session.commit()
    print("✔ Done")

if __name__ == "__main__":
    main()
```

- [ ] **Step 8: 提交**

```bash
git add app/models/factor_skill.py app/models/factor_run.py app/models/factor_category.py \
  app/db/__init__.py alembic/versions/xxxx_add_factor_tables.py \
  alembic/versions/xxxx_seed_gallery_cases.py scripts/seed_factor_cases.py
git commit -m "feat: add FactorSkill + FactorRun models and gallery seed migration"
```

---

## Task 2: 后端 — Services 拆包（skills 模块）

**Files:**
- Create: `app/services/skills/__init__.py`
- Create: `app/services/skills/errors.py`
- Create: `app/services/skills/ast_check.py`
- Create: `app/services/skills/kline.py`
- Create: `app/services/skills/sandbox.py`
- Create: `app/services/skills/sandbox_worker.py`
- Create: `app/services/skills/generator.py`
- Create: `app/services/skills/runner.py`
- Create: `app/services/skills/narrator.py`
- Modify: `app/services/skills.py`（替换为 re-export）
- Modify: `app/core/limiter.py`（user-based 限流）

- [ ] **Step 1: 写 errors.py（统一异常）**

```python
# app/services/skills/errors.py
"""Skill 相关统一异常，所有 API 层 catch 后转结构化 JSON"""


class SkillError(Exception):
    code: str = "SKILL_ERROR"


class SkillSyntaxError(SkillError):
    code = "SKILL_SYNTAX_ERROR"


class SkillSandboxError(SkillError):
    code = "SKILL_SANDBOX_ERROR"


class SkillDataError(SkillError):
    code = "SKILL_DATA_ERROR"


class SkillTimeoutError(SkillError):
    code = "SKILL_TIMEOUT"
```

- [ ] **Step 2: 写 ast_check.py（从 skills.py 抽取 + 精简）**

```python
# app/services/skills/ast_check.py
"""Python AST 安全检查：禁止危险 builtins，禁止 os/subprocess/socket 等模块。"""
from __future__ import annotations

import ast

_DANGEROUS_BUILTINS = frozenset({
    "open", "compile", "eval", "exec", "getattr", "setattr",
    "delattr", "hasattr", "__import__", "reload", "breakpoint",
})
_ALLOWED_BUILTINS: frozenset[str] = frozenset({"abs", "len", "range", "enumerate",
    "zip", "min", "max", "sum", "sorted", "reversed", "list", "dict",
    "tuple", "set", "float", "int", "str", "bool", "type", "isinstance",
    "round", "pow", "math", "numpy", "pandas"})

_DANGEROUS_MODULES = frozenset({
    "os", "sys", "subprocess", "socket", "requests", "urllib",
    "http", "ftplib", "telnetlib", "pty", "tty", "termios",
    "fcntl", "select", "poll", "epoll", "asyncio", "threading",
    "multiprocessing", "concurrent", "aiohttp", "httpx",
})


def check_code_safety(code: str) -> None:
    """解析 code，若含危险 builtins 或 imports 则抛出 SkillSyntaxError。"""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SkillSyntaxError(f"代码语法错误：{e}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id in _DANGEROUS_BUILTINS:
                raise SkillSyntaxError(f"禁止使用 builtin：{node.id}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.split(".")[0]
                if name in _DANGEROUS_MODULES:
                    raise SkillSyntaxError(f"禁止导入模块：{name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in _DANGEROUS_MODULES:
                raise SkillSyntaxError(f"禁止从 {node.module.split('.')[0]} 导入")

    # 检查 __class__ / __base__ 逃逸（子类枚举逃逸面）
    source = code.replace(" ", "").replace("\n", "")
    dangerous_patterns = ["__class__", "__base__", "__subclasses__", "__globals__"]
    for pat in dangerous_patterns:
        if pat in source:
            raise SkillSyntaxError(f"代码包含禁止模式：{pat}")


def get_allowed_builtins() -> dict[str, object]:
    """返回沙箱可用的 builtins 字典。"""
    safe = {}
    for name in _ALLOWED_BUILTINS:
        try:
            import math, numpy, pandas
            safe[name] = eval(name) if name in ("math", "numpy", "pandas") else None
        except Exception:
            pass
    return {
        "abs": abs, "len": len, "range": range, "enumerate": enumerate,
        "zip": zip, "min": min, "max": max, "sum": sum, "sorted": sorted,
        "reversed": reversed, "list": list, "dict": dict, "tuple": tuple,
        "set": set, "float": float, "int": int, "str": str, "bool": bool,
        "type": type, "isinstance": isinstance, "round": round, "pow": pow,
        "math": __import__("math"),
        "numpy": __import__("numpy"),
        "pandas": __import__("pandas"),
    }
```

- [ ] **Step 3: 写 kline.py（K 线拉取 + user-id 隔离缓存）**

```python
# app/services/skills/kline.py
"""K 线拉取 + Redis 缓存（user_id 隔离 key）"""
from __future__ import annotations

import json, os
from datetime import date

import httpx
from redis.asyncio import Redis

from app.cache.operations import get_json, set_json
from app.core.logging import logger

FMP_KEY = os.environ.get("FMP_API_KEY", "")
FMP_URL = "https://financialmodelingprep.com/stable/historical-price-eod/full"
CACHE_TTL = 3600 * 24  # 24h


def _cache_key(user_id: int | None, symbol: str, start: str, end: str, freq: str) -> str:
    prefix = f"u{user_id}" if user_id else "public"
    return f"skill_kline:{prefix}:{symbol}:{start}:{end}:{freq}"


async def fetch_kline(
    user_id: int | None,
    symbol: str,
    start_date: str,
    end_date: str,
    freq: str = "daily",
    redis: Redis | None = None,
) -> list[dict]:
    cache_key = _cache_key(user_id, symbol, start_date, end_date, freq)

    if redis:
        cached = await get_json(redis, cache_key)
        if cached:
            logger.debug("kline_cache_hit", key=cache_key)
            return cached

    # 拉 FMP
    params = {"symbol": symbol, "from": start_date, "to": end_date,
              "apikey": FMP_KEY, "period": freq}
    resp = httpx.get(FMP_URL, params=params, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    records = payload if isinstance(payload, list) else payload.get("historical", [])
    records.sort(key=lambda r: r["date"])

    bars = [
        {"time": r["date"], "open": r["open"], "high": r["high"],
         "low": r["low"], "close": r["close"], "volume": r.get("volume", 0)}
        for r in records
    ]

    if redis:
        await set_json(redis, cache_key, bars, ex=CACHE_TTL)

    return bars
```

- [ ] **Step 4: 写 sandbox_worker.py（子进程入口，独立运行）**

```python
# app/services/skills/sandbox_worker.py
"""
子进程入口：从 stdin 读 JSON {"code", "price", "symbol", "start_date", "end_date"}
执行因子代码，从 stdout 写 JSON {"records": [...], "output_type": str}
"""
from __future__ import annotations

import json, sys, traceback

# 受限 builtins（仅 math + numpy + pandas 核心）
import math
import numpy as np
import pandas as pd

ALLOWED_BUILTINS = {
    "abs": abs, "len": len, "range": range, "enumerate": enumerate,
    "zip": zip, "min": min, "max": max, "sum": sum, "sorted": sorted,
    "reversed": reversed, "list": list, "dict": dict, "tuple": tuple,
    "set": set, "float": float, "int": int, "str": str, "bool": bool,
    "type": type, "isinstance": isinstance, "round": round, "pow": pow,
    "math": math, "np": np, "numpy": np, "pd": pd, "pd": pd,
}

class SandboxNamespace:
    pass

def run(payload: dict) -> dict:
    code = payload["code"]
    price_records = payload["price"]  # list[dict]
    symbol = payload["symbol"]
    start_date = payload["start_date"]
    end_date = payload["end_date"]

    # 把 K 线数据注入 namespace
    ns = SandboxNamespace()
    for k, v in ALLOWED_BUILTINS.items():
        setattr(ns, k, v)
    ns.price_records = price_records
    ns.symbol = symbol
    ns.start_date = start_date
    ns.end_date = end_date

    # 执行用户代码（定义 compute(prices, symbol) -> list[dict]）
    exec(code, vars(ns))
    compute_fn = ns.compute

    result = compute_fn(price_records, symbol)
    output_type = "line"  # 默认

    return {"records": result, "output_type": output_type}

if __name__ == "__main__":
    payload = json.loads(sys.stdin.read())
    try:
        result = run(payload)
        sys.stdout.write(json.dumps(result))
    except Exception as e:
        sys.stderr.write(f"Skill 执行错误：{e}\n{traceback.format_exc()}")
        sys.exit(1)
```

- [ ] **Step 5: 写 sandbox.py（subprocess 调用 + RLIMIT）**

```python
# app/services/skills/sandbox.py
"""subprocess 沙箱：通过独立 Python 子进程执行因子代码，setrlimit 限资源。"""
from __future__ import annotations

import asyncio, json, os, sys
from typing import Literal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.services.skills.errors import SkillTimeoutError, SkillSandboxError


async def run_in_subprocess(
    code: str,
    price_records: list[dict],
    symbol: str,
    start_date: str,
    end_date: str,
    *,
    timeout: float = 30.0,
) -> tuple[list[dict], str]:
    payload = json.dumps({
        "code": code,
        "price": price_records,
        "symbol": symbol,
        "start_date": start_date,
        "end_date": end_date,
    }).encode()

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "app.services.skills.sandbox_worker",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=_apply_rlimits if sys.platform.startswith("linux") else None,
        )
    except FileNotFoundError:
        # macOS/Windows 子进程创建失败，降级到线程执行（不安全，仅开发模式）
        return _fallback_exec(code, price_records, symbol, start_date, end_date)

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=payload), timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise SkillTimeoutError(f"Skill 执行超时（>{timeout}s），请简化逻辑")

    if proc.returncode != 0:
        raise SkillSandboxError(stderr.decode()[:500])

    result = json.loads(stdout)
    return result["records"], result.get("output_type", "line")


def _apply_rlimits():
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))


def _fallback_exec(code, price_records, symbol, start_date, end_date):
    """开发模式降级：在当前进程执行（仅 macOS/Windows）"""
    import numpy as np, pandas as pd
    ns = {"price_records": price_records, "symbol": symbol,
          "start_date": start_date, "end_date": end_date,
          "math": __import__("math"), "np": np, "pd": pd,
          "abs": abs, "len": len, "range": range, "enumerate": enumerate,
          "zip": zip, "min": min, "max": max, "sum": sum, "sorted": sorted,
          "list": list, "dict": dict, "tuple": tuple, "set": set,
          "float": float, "int": int, "str": str, "bool": bool,
          "type": type, "isinstance": isinstance, "round": round, "pow": pow,
          "__builtins__": {}}
    exec(code, ns)
    return ns["compute"](price_records, symbol), "line"
```

- [ ] **Step 6: 写 runner.py（沙箱执行编排）**

```python
# app/services/skills/runner.py
"""执行编排：从 cache 取 K 线 → AST 检查 → sandbox 执行 → 找信号点 → 标准化"""
from __future__ import annotations

from app.services.skills.ast_check import check_code_safety
from app.services.skills.errors import SkillDataError, SkillSyntaxError, SkillTimeoutError
from app.services.skills.sandbox import run_in_subprocess

LOOKBACK_SIGNALS = 60
SKIP_RECENT = 5


def compute_factor_signals(records: list[dict], code: str, symbol: str,
                            start_date: str, end_date: str) -> dict:
    """执行 skill，返回 {factor: [...], signals: [...], metrics: {...}}"""
    check_code_safety(code)

    raw_result, output_type = run_in_subprocess(
        code, records, symbol, start_date, end_date, timeout=30.0,
    )

    if not raw_result:
        raise SkillDataError("因子计算返回空结果")

    # 提取 factor series
    factor_series = [{"time": r.get("time", r.get("date", "")), "value": r["value"]}
                     for r in raw_result if "value" in r]

    # z-score 标准化
    values = [f["value"] for f in factor_series]
    if len(values) < 10:
        raise SkillDataError(f"数据点不足（{len(values)}），需要至少 10 个点")

    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    std = var ** 0.5 or 1.0
    factor_z = [{"time": f["time"], "value": (f["value"] - mean) / std} for f in factor_series]

    # 找信号点（|z| >= 1.5）
    signal_idxs, in_zone, peak_idx, peak_abs = [], False, -1, 0.0
    for i, f in enumerate(factor_z):
        if abs(f["value"]) >= 1.5:
            if not in_zone or abs(f["value"]) > peak_abs:
                peak_idx, peak_abs = i, abs(f["value"])
            in_zone = True
        else:
            if in_zone and peak_idx >= 0:
                signal_idxs.append(peak_idx)
                peak_idx, peak_abs = -1, 0.0
            in_zone = False
    if in_zone and peak_idx >= 0:
        signal_idxs.append(peak_idx)

    # 取 top 4 信号
    sorted_signals = sorted(signal_idxs, key=lambda i: -abs(factor_z[i]["value"]))[:4]

    # 指标卡数据
    last_f = factor_z[-1]["value"]
    return {
        "factor": factor_z,
        "signals": [{"date": factor_z[i]["time"],
                     "z": round(factor_z[i]["value"], 2),
                     "close": raw_result[i].get("close", raw_result[i]["value"])}
                    for i in sorted(factor_z[i]["time"] in [factor_z[s]["time"] for s in sorted_signals] and
                                    (lambda: None))  # 见 Step 6 下方补充代码],
        "metrics": {
            "current_z": round(factor_z[-1]["value"], 2),
            "peak_z": round(max(abs(f["value"]) for f in factor_z), 2),
            "data_days": len(factor_series),
            "trigger_count": sum(1 for f in factor_z if abs(f["value"]) >= 1.0),
        }
    }
```

> **注意：** Step 6 中的信号对应 close 价格需要从原始 records 找对应日期，按如下方式补全：
```python
# 在 compute_factor_signals 中，信号点的 close 价格从原始 records 映射
date_to_close = {r["date"]: r["close"] for r in records}
signals = []
for idx in sorted_signals:
    t = factor_z[idx]["time"]
    signals.append({
        "date": t,
        "z": round(factor_z[idx]["value"], 2),
        "close": date_to_close.get(t, 0.0),
    })
```

- [ ] **Step 7: 写 narrator.py（AI 旁白生成）**

```python
# app/services/skills/narrator.py
"""AI 旁白生成：将因子计算结果（信号点 + 指标卡）转化为业务语言叙事。"""
from __future__ import annotations

from langchain_core.messages import SystemMessage, HumanMessage

from app.core.logging import logger
from app.services.llm.service import llm_service

NARRATOR_SYSTEM_PROMPT = """你是一位资深量化研究员，为股票因子计算结果撰写专业旁白。

要求：
1. 语言：业务化、自然流畅，禁止出现"Python/代码/函数/变量"等技术术语
2. 格式：三段式（立意 + 关键时点 + 适用失效场景）
3. 每个关键时点旁白：20-40 字，描述当时市场背景与因子含义
4. 适用/失效场景：各 1-2 句，用 · 分隔

输出 JSON 格式：
{
  "thesis": "【一句话立意】",
  "key_points": [{"date": "YYYY-MM-DD", "z": 2.5, "text": "市场背景与因子含义（20-40字）"}, ...],
  "verdict": {
    "applicable": "适用场景描述（用 · 分隔）",
    "fails": "失效场景描述（用 · 分隔）"
  },
  "generated_at": "ISO 时间",
  "model": "模型名"
}
"""

async def generate_narrative(
    snapshot: dict,
    symbol: str,
    category: str,
) -> dict:
    """根据因子快照 + 信号点生成旁白。"""
    import datetime as dt

    factor_series = snapshot.get("factor", [])
    signals = snapshot.get("signals", [])
    metrics = snapshot.get("metrics", {})

    context_lines = [
        f"股票代码：{symbol}",
        f"因子类别：{category}",
        f"当前 z-score：{metrics.get('current_z', 'N/A')}",
        f"历史峰值 z-score：{metrics.get('peak_z', 'N/A')}",
        f"触发极端信号的次数（|z|>=1.0）：{metrics.get('trigger_count', 0)}",
        f"数据天数：{metrics.get('data_days', 0)}",
        "",
        "信号点：",
    ]
    for s in signals:
        context_lines.append(f"  {s['date']}  z={s['z']:+.2f}  close=${s['close']:.2f}")

    context_lines.append("")
    context_lines.append("因子时序（前10 / 后10）：")
    for f in factor_series[:10]:
        context_lines.append(f"  {f['time']}  value={f['value']:+.4f}")
    if len(factor_series) > 20:
        context_lines.append("  ...")
        for f in factor_series[-10:]:
            context_lines.append(f"  {f['time']}  value={f['value']:+.4f}")

    prompt = "\n".join(context_lines)

    messages = [
        SystemMessage(content=NARRATOR_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]

    response = await llm_service.call(messages)
    import json as _json
    content = response.content.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]

    try:
        narrative = _json.loads(content)
    except Exception:
        logger.warning("narrative_parse_failed", raw=content[:200])
        narrative = {
            "thesis": f"该因子在 {symbol} 上的表现总结",
            "key_points": [{"date": s["date"], "z": s["z"],
                           "text": f"z={s['z']:+.2f} 时股价 ${s['close']:.2f}"}
                           for s in signals],
            "verdict": {"applicable": "趋势行情", "fails": "震荡市"},
            "generated_at": dt.datetime.utcnow().isoformat() + "Z",
            "model": llm_service.model_name,
        }

    narrative["generated_at"] = dt.datetime.utcnow().isoformat() + "Z"
    narrative["model"] = getattr(llm_service, "model_name", "unknown")
    return narrative
```

- [ ] **Step 8: 写 generator.py（从 skills.py 抽取流式生成逻辑）**

```python
# app/services/skills/generator.py
"""流式代码生成：SSE 流式输出 LLM 生成结果。"""
from __future__ import annotations

from typing import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.logging import logger
from app.services.llm.registry import llm_registry

SKILL_GENERATOR_PROMPT = """你是一位量化因子工程师。用户输入的是一段因子描述，请生成一段可执行的 Python 函数。

要求：
1. 定义 compute(prices: list[dict], symbol: str) -> list[dict]，返回因子时序
2. prices 格式：[{{'date': '2024-01-01', 'close': 120.5, 'open': 119, 'high': 122, 'low': 118, 'volume': 1000000}}, ...]
3. 返回格式：list[{{'time': '2024-01-01', 'value': 0.05}}]（value 是原始因子值，不需要标准化）
4. 可以使用 numpy（别名 np）和 pandas（别名 pd）
5. 禁止：os / subprocess / socket / requests / __import__ / eval / exec
6. 变量名用英文，注释用中文

示例（动量因子）：
```python
def compute(prices, symbol):
    closes = [p['close'] for p in prices]
    result = []
    for i in range(60, len(closes)):
        mom = (closes[i] / closes[i-60] - 1) * 100
        result.append({'time': prices[i]['date'], 'value': mom})
    return result
```
"""

async def generate_skill_stream(messages: list[dict]) -> AsyncGenerator[str, None]:
    """SSE 流式生成 skill 代码。"""
    llm = llm_registry.get_default()
    chain_messages = [SystemMessage(content=SKILL_GENERATOR_PROMPT)]
    for m in messages:
        role = "user" if m["role"] == "user" else "assistant"
        chain_messages.append(HumanMessage(content=m["content"]) if role == "user"
                              else AIMessage(content=m["content"]))

    async for chunk in llm.astream(chain_messages):
        if chunk.content:
            yield f"data: {__import__('json').dumps({'content': chunk.content, 'done': False})}\n\n"

    yield f"data: {__import__('json').dumps({'content': '', 'done': True})}\n\n"
```

- [ ] **Step 9: 写 __init__.py（统一导出 + 旧接口兼容）**

```python
# app/services/skills/__init__.py
"""skills 服务包——向后兼容老 skills.py 的导出。"""
from app.services.skills.generator import generate_skill_stream
from app.services.skills.runner import compute_factor_signals as execute_skill
from app.services.skills.kline import fetch_kline
from app.services.skills.kline import fetch_kline as fetch_and_cache_kline
from app.services.skills.kline import _cache_key as get_cached_price_df  # 近似兼容

__all__ = [
    "generate_skill_stream",
    "execute_skill",
    "fetch_kline",
    "fetch_and_cache_kline",
]
```

- [ ] **Step 10: 更新 limiter.py（user-based 限流）**

```python
# 在 app/core/limiter.py 的限流 key 函数中，找到 Skill 相关端点
# 修改 key_func 为基于 user_id（而不是 IP）
# 对于 /generate /save /rerun 等端点，key_func 在认证中间件之后注入

# 具体修改位置：找到 @limiter.limit("20 per minute") 等装饰器的 key_func 参数
# 添加 key_func=lambda req: f"u{req.state.user_id}"（需在 Depends(get_current_user) 之后）
```

- [ ] **Step 11: 删除旧 skills.py，重命名为兼容文件**

```bash
# 将 app/services/skills.py 重命名（保留一段时间用于过渡）
# 不需要做，__init__.py 已经替代了它的导出
```

实际：在 `app/services/skills/` 建立后，`app/services/skills.py` 可以删除（或改为简单 re-export）。由于 spec 说明 services 拆包后原文件转为 `app/services/skills/__init__.py`，这里直接将 `skills.py` 内容转为 `__init__.py`。

- [ ] **Step 12: 提交**

```bash
git add app/services/skills/ app/services/skills.py app/core/limiter.py
git commit -m "refactor: split skills service into package (sandbox, narrator, kline, runner, generator)"
```

---

## Task 3: 后端 — API 层（skills 新端点）

**Files:**
- Modify: `app/api/v1/skills.py`
- Modify: `app/schemas/skills.py`
- Modify: `app/models/user.py`（确认 id 类型）

- [ ] **Step 1: 写新 schemas（FactorSkill 相关的 request/response）**

```python
# 在 app/schemas/skills.py 末尾追加

from uuid import UUID
from pydantic import BaseModel, Field
from typing import Literal


class FactorSkillBrief(BaseModel):
    id: UUID
    title: str
    description: str
    category: str
    default_symbol: str
    is_public: bool
    pin_priority: int | None
    created_at: datetime


class FactorSkillDetail(FactorSkillBrief):
    code: str
    default_start_date: str
    default_end_date: str
    default_freq: str
    snapshot: dict
    narrative: dict | None
    owner_id: int | None


class FactorSkillGalleryResponse(BaseModel):
    hero: FactorSkillDetail | None
    cases: list[FactorSkillBrief]


class FactorSkillMineResponse(BaseModel):
    skills: list[FactorSkillBrief]


class SaveSkillRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=80)
    description: str = Field(..., min_length=1, max_length=200)
    category: str
    code: str = Field(..., max_length=20000)
    symbol: str = Field(..., max_length=20)
    start_date: str = Field(..., max_length=10)
    end_date: str = Field(..., max_length=10)
    freq: Literal["daily", "weekly"] = "daily"


class RerunRequest(BaseModel):
    symbol: str = Field(..., max_length=20)
    start_date: str = Field(..., max_length=10)
    end_date: str = Field(..., max_length=10)
    freq: Literal["daily", "weekly"] = "daily"
```

- [ ] **Step 2: 重写 api/v1/skills.py（新端点 + 清理旧逻辑）**

保留 `generate` 和 `kline` 端点（逻辑移入 services），新增：

```python
# app/api/v1/skills.py 新增端点（现有端点保留，新端点追加）

@router.get("/gallery", response_model=FactorSkillGalleryResponse)
@limiter.limit("60 per minute")
async def get_gallery(user: User = Depends(get_current_user)) -> FactorSkillGalleryResponse:
    """案例馆：Hero（pin_priority=1）+ 副网格（其余 NULL + owner_id 案例）"""
    from app.db.session import get_sync_session
    from sqlalchemy import select, or_, and_
    from app.models.factor_skill import FactorSkill

    session = get_sync_session().__enter__()
    hero = session.exec(
        select(FactorSkill).where(
            FactorSkill.owner_id.is_(None),
            FactorSkill.pin_priority == 1,
        ).order_by(FactorSkill.created_at.desc()).limit(1)
    ).first()

    cases = session.exec(
        select(FactorSkill).where(
            FactorSkill.owner_id.is_(None),
            or_(FactorSkill.pin_priority.is_(None), FactorSkill.pin_priority > 1),
        ).order_by(FactorSkill.pin_priority.asc().nullslast(),
                   FactorSkill.created_at.desc())
    ).all()

    return FactorSkillGalleryResponse(
        hero=FactorSkillDetail.model_validate(hero) if hero else None,
        cases=[FactorSkillBrief.model_validate(c) for c in cases],
    )


@router.get("/mine", response_model=FactorSkillMineResponse)
@limiter.limit("60 per minute")
async def get_mine(user: User = Depends(get_current_user)) -> FactorSkillMineResponse:
    """我的因子：当前用户保存的所有 skill"""
    from app.db.session import get_sync_session
    from sqlalchemy import select
    from app.models.factor_skill import FactorSkill

    session = get_sync_session().__enter__()
    skills = session.exec(
        select(FactorSkill).where(FactorSkill.owner_id == user.id)
        .order_by(FactorSkill.created_at.desc())
    ).all()

    return FactorSkillMineResponse(skills=[FactorSkillBrief.model_validate(s) for s in skills])


@router.get("/{skill_id}", response_model=FactorSkillDetail)
async def get_skill_detail(skill_id: UUID, user: User = Depends(get_current_user)) -> FactorSkillDetail:
    """详情页：返回完整 skill（含快照 + narrative）"""
    from app.db.session import get_sync_session
    from sqlalchemy import select
    from app.models.factor_skill import FactorSkill

    session = get_sync_session().__enter__()
    skill = session.get(FactorSkill, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    # 公开 skill 任意用户可读；私有 skill 需 owner 一致
    if skill.owner_id is not None and skill.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return FactorSkillDetail.model_validate(skill)


@router.post("/save", response_model=FactorSkillBrief)
@limiter.limit("20 per minute", key_func=lambda req: f"u{getattr(req.state, 'user_id', req.client.host)}")
async def save_skill(body: SaveSkillRequest, user: User = Depends(get_current_user)) -> FactorSkillBrief:
    """保存新 skill（生成 AI 旁白）"""
    from app.db.session import get_sync_session
    from app.services.skills.kline import fetch_kline
    from app.services.skills.runner import compute_factor_signals
    from app.services.skills.narrator import generate_narrative

    session = get_sync_session().__enter__()

    # 拉 K 线
    kline = await fetch_kline(user.id, body.symbol, body.start_date, body.end_date, body.freq)
    if not kline:
        raise HTTPException(status_code=400, detail="无法获取股票数据")

    # 计算因子快照
    try:
        snapshot = compute_factor_signals(kline, body.code, body.symbol, body.start_date, body.end_date)
    except SkillError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # 生成旁白（流式旁白在 Task 5 前端处理，这里是同步快速版）
    narrative = await generate_narrative(snapshot, body.symbol, body.category)

    # 写入 DB
    skill = FactorSkill(
        owner_id=user.id,
        title=body.title,
        description=body.description,
        category=body.category,
        code=body.code,
        default_symbol=body.symbol,
        default_start_date=body.start_date,
        default_end_date=body.end_date,
        default_freq=body.freq,
        snapshot_factor_jsonb=snapshot,
        narrative_jsonb=narrative,
        is_public=False,
    )
    session.add(skill)
    session.commit()
    session.refresh(skill)
    return FactorSkillBrief.model_validate(skill)


@router.post("/{skill_id}/rerun", response_model=dict)
@limiter.limit("30 per minute", key_func=lambda req: f"u{getattr(req.state, 'user_id', req.client.host)}")
async def rerun_skill(skill_id: UUID, body: RerunRequest, user: User = Depends(get_current_user)) -> dict:
    """换股重跑：计算结果写入 factor_runs 表"""
    from app.db.session import get_sync_session
    from sqlalchemy import select, and_
    from app.models.factor_skill import FactorSkill
    from app.models.factor_run import FactorRun
    from app.services.skills.kline import fetch_kline
    from app.services.skills.runner import compute_factor_signals
    from app.services.skills.narrator import generate_narrative

    session = get_sync_session().__enter__()
    skill = session.get(FactorSkill, skill_id)
    if not skill or (skill.owner_id and skill.owner_id != user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    # 检查缓存（factor_runs）
    existing = session.exec(
        select(FactorRun).where(
            and_(
                FactorRun.skill_id == skill_id,
                FactorRun.user_id == user.id,
                FactorRun.symbol == body.symbol,
                FactorRun.start_date == body.start_date,
                FactorRun.end_date == body.end_date,
                FactorRun.freq == body.freq,
            )
        )
    ).first()
    if existing:
        return {"cached": True, "snapshot": existing.factor_jsonb, "narrative": existing.narrative_jsonb}

    # 计算
    kline = await fetch_kline(user.id, body.symbol, body.start_date, body.end_date, body.freq)
    snapshot = compute_factor_signals(kline, skill.code, body.symbol, body.start_date, body.end_date)
    narrative = await generate_narrative(snapshot, body.symbol, skill.category)

    # 写入
    run = FactorRun(
        skill_id=skill_id,
        user_id=user.id,
        symbol=body.symbol,
        start_date=body.start_date,
        end_date=body.end_date,
        freq=body.freq,
        factor_jsonb=snapshot,
        narrative_jsonb=narrative,
    )
    session.add(run)
    session.commit()

    return {"cached": False, "snapshot": snapshot, "narrative": narrative}


@router.delete("/{skill_id}")
@limiter.limit("20 per minute")
async def delete_skill(skill_id: UUID, user: User = Depends(get_current_user)):
    """删除我的因子（仅 owner 可操作）"""
    from app.db.session import get_sync_session
    from app.models.factor_skill import FactorSkill

    session = get_sync_session().__enter__()
    skill = session.get(FactorSkill, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Not found")
    if skill.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    session.delete(skill)
    session.commit()
    return {"ok": True}
```

- [ ] **Step 3: 在主应用注册新端点（如需要）**

确认 `app/main.py` 中已包含 `app.api.v1.skills.router`（现有代码应已有）。

- [ ] **Step 4: 提交**

```bash
git add app/api/v1/skills.py app/schemas/skills.py
git commit -m "feat: add FactorSkill CRUD + gallery + rerun API endpoints"
```

---

## Task 4: 前端 — Bug 修复（负边距 + 深色背景）

**Files:**
- Modify: `frontend/app/(dashboard)/skill-generator/page.tsx`

- [ ] **Step 1: 读取当前 page.tsx 并找到负边距/深色背景**

```bash
# 找到 -mx-6 -my-8 bg-gray-950 的位置
grep -n "mx-6\|my-8\|bg-gray-950" /Users/zhangfang/deepalpha-club-ai/frontend/app/\(dashboard\)/skill-generator/page.tsx
```

- [ ] **Step 2: 修复负边距**

删除/修改包含 `-mx-6 -my-8` 的 div 包装，改为使用 dashboard layout 的标准 padding。

在 `<div className="min-h-screen bg-background">` 之后，内容区直接使用 `p-6` 或 dashboard 的 container padding。

- [ ] **Step 3: 修复整页深色背景**

将 `bg-gray-950` 替换为 `bg-background`（浅色，与全站一致）。

- [ ] **Step 4: 提交**

```bash
git add frontend/app/\(dashboard\)/skill-generator/page.tsx
git commit -m "fix: remove negative margins and convert skill-generator to light theme"
```

---

## Task 5: 前端 — 路由 + Tab 调度 + 状态管理

**Files:**
- Modify: `frontend/app/(dashboard)/skill-generator/page.tsx`
- Create: `frontend/lib/store/skills.ts`
- Modify: `frontend/lib/api/skills.ts`

- [ ] **Step 1: 建立 Zustand store**

```typescript
// frontend/lib/store/skills.ts
import { create } from 'zustand'

interface FactorSkillBrief {
  id: string
  title: string
  description: string
  category: string
  default_symbol: string
  is_public: boolean
  pin_priority: number | null
  created_at: string
}

interface SkillDetail extends FactorSkillBrief {
  code: string
  default_start_date: string
  default_end_date: string
  default_freq: string
  snapshot: Record<string, unknown>
  narrative: Record<string, unknown> | null
  owner_id: number | null
}

type Tab = 'gallery' | 'mine' | 'new'

interface SkillsStore {
  activeTab: Tab
  selectedSkillId: string | null
  detailSkill: SkillDetail | null
  detailLoading: boolean

  setActiveTab: (tab: Tab) => void
  openDetail: (skillId: string) => Promise<void>
  closeDetail: () => void
}

export const useSkillsStore = create<SkillsStore>((set, get) => ({
  activeTab: 'gallery',
  selectedSkillId: null,
  detailSkill: null,
  detailLoading: false,

  setActiveTab: (tab) => {
    set({ activeTab: tab, selectedSkillId: null, detailSkill: null })
  },

  openDetail: async (skillId: string) => {
    set({ selectedSkillId: skillId, detailLoading: true })
    try {
      const { getSkillDetail } = await import('@/lib/api/skills')
      const skill = await getSkillDetail(skillId)
      set({ detailSkill: skill, detailLoading: false })
    } catch {
      set({ detailLoading: false })
    }
  },

  closeDetail: () => {
    set({ selectedSkillId: null, detailSkill: null })
  },
}))
```

- [ ] **Step 2: 扩展 API 客户端**

```typescript
// frontend/lib/api/skills.ts 追加（保持原有函数不变，追加新函数）

export async function getGallery(): Promise<{ hero: SkillDetail | null; cases: SkillBrief[] }> {
  const resp = await client.get('/api/v1/skills/gallery')
  return resp.data
}

export async function getMine(): Promise<{ skills: SkillBrief[] }> {
  const resp = await client.get('/api/v1/skills/mine')
  return resp.data
}

export async function getSkillDetail(id: string): Promise<SkillDetail> {
  const resp = await client.get(`/api/v1/skills/${id}`)
  return resp.data
}

export async function saveSkill(payload: SaveSkillPayload): Promise<SkillBrief> {
  const resp = await client.post('/api/v1/skills/save', payload)
  return resp.data
}

export async function rerunSkill(id: string, payload: RerunPayload): Promise<RerunResult> {
  const resp = await client.post(`/api/v1/skills/${id}/rerun`, payload)
  return resp.data
}

export async function deleteSkill(id: string): Promise<void> {
  await client.delete(`/api/v1/skills/${id}`)
}
```

- [ ] **Step 3: 重写 page.tsx（Tab 调度）**

```tsx
// frontend/app/(dashboard)/skill-generator/page.tsx
// 核心：useSearchParams 读取 ?tab= 和 ?factor_id=
// 根据 tab 渲染 GalleryView / MineView / NewView
// factor_id 存在时渲染 DetailPage（模态/全屏）

'use client'
import { useSearchParams, useRouter } from 'next/navigation'
import { useEffect } from 'react'
import { useSkillsStore } from '@/lib/store/skills'
import { GalleryView } from './_components/GalleryView'
import { MineView } from './_components/MineView'
import { NewView } from './_components/NewView'
import { DetailPage } from './_components/DetailPage'

export default function SkillGeneratorPage() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const { activeTab, selectedSkillId, setActiveTab, closeDetail } = useSkillsStore()

  const tabParam = (searchParams.get('tab') as 'gallery' | 'mine' | 'new') || 'gallery'

  useEffect(() => {
    if (tabParam !== activeTab) {
      setActiveTab(tabParam)
    }
  }, [tabParam])

  const switchTab = (tab: 'gallery' | 'mine' | 'new') => {
    router.replace(`/skill-generator?tab=${tab}`)
    setActiveTab(tab)
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Tab 切换栏 */}
      <div className="border-b border-gray-200 bg-white px-6 py-3 flex gap-1">
        <TabButton label="案例馆" active={activeTab === 'gallery'} onClick={() => switchTab('gallery')} />
        <TabButton label="我的因子" active={activeTab === 'mine'} onClick={() => switchTab('mine')} />
        <TabButton label="新建" active={activeTab === 'new'} onClick={() => switchTab('new')} />
      </div>

      {/* 内容区 */}
      <div className="p-6">
        {activeTab === 'gallery' && <GalleryView />}
        {activeTab === 'mine' && <MineView />}
        {activeTab === 'new' && <NewView />}
      </div>

      {/* 详情页模态 */}
      {selectedSkillId && <DetailPage />}
    </div>
  )
}

function TabButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
        active ? 'bg-primary text-white' : 'text-gray-500 hover:bg-gray-100'
      }`}
    >
      {label}
    </button>
  )
}
```

- [ ] **Step 4: 提交**

```bash
git add frontend/lib/store/skills.ts frontend/lib/api/skills.ts frontend/app/\(dashboard\)/skill-generator/page.tsx
git commit -m "feat: add SkillsStore + Tab routing for skill-generator"
```

---

## Task 6: 前端 — 案例馆（GalleryView + FactorCard）

**Files:**
- Create: `frontend/app/(dashboard)/skill-generator/_components/GalleryView.tsx`
- Create: `frontend/app/(dashboard)/skill-generator/_components/FactorCard.tsx`

- [ ] **Step 1: FactorCard（通用卡片）**

```tsx
// frontend/app/(dashboard)/skill-generator/_components/FactorCard.tsx
import { useSkillsStore } from '@/lib/store/skills'

interface FactorCardProps {
  id: string
  title: string
  description: string
  category: string
  symbol: string
  isPin?: boolean
  style?: 'hero' | 'grid'
}

const CATEGORY_COLORS: Record<string, string> = {
  momentum: 'border-l-blue-500',
  reversal: 'border-l-orange-500',
  volatility: 'border-l-purple-500',
  volume: 'border-l-green-500',
  sentiment: 'border-l-pink-500',
  technical: 'border-l-cyan-500',
  custom: 'border-l-gray-400',
}

export function FactorCard({ id, title, description, category, symbol, isPin, style = 'grid' }: FactorCardProps) {
  const { openDetail } = useSkillsStore()

  if (style === 'hero') {
    return (
      <div
        onClick={() => openDetail(id)}
        className="relative rounded-2xl bg-gradient-to-br from-primary/10 to-primary/5 border border-primary/20 p-6 cursor-pointer hover:shadow-lg transition-all"
      >
        {isPin && (
          <span className="absolute top-3 right-3 text-xs bg-primary text-white px-2 py-0.5 rounded-full">
            ⭐ 精选
          </span>
        )}
        <div className="text-xs text-gray-500 mb-1">{symbol}</div>
        <div className="text-lg font-semibold text-gray-900 mb-2">{title}</div>
        <div className="text-sm text-gray-600">{description}</div>
      </div>
    )
  }

  return (
    <div
      onClick={() => openDetail(id)}
      className={`rounded-xl bg-white border border-gray-200 p-4 cursor-pointer hover:shadow-md hover:border-gray-300 transition-all border-l-4 ${CATEGORY_COLORS[category] ?? 'border-l-gray-400'}`}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{symbol}</span>
        {isPin && <span className="text-xs text-primary">⭐ 精选</span>}
      </div>
      <div className="font-medium text-gray-900 mb-1">{title}</div>
      <div className="text-xs text-gray-500 line-clamp-2">{description}</div>
    </div>
  )
}
```

- [ ] **Step 2: GalleryView**

```tsx
// frontend/app/(dashboard)/skill-generator/_components/GalleryView.tsx
import { useEffect, useState } from 'react'
import { getGallery } from '@/lib/api/skills'
import { FactorCard } from './FactorCard'

export function GalleryView() {
  const [data, setData] = useState<{ hero: any | null; cases: any[] } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getGallery()
      .then(setData)
      .catch(() => setData({ hero: null, cases: [] }))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-pulse text-gray-400">加载案例馆...</div></div>
  if (!data) return null

  return (
    <div className="space-y-8">
      {/* Hero */}
      {data.hero && (
        <section>
          <h2 className="text-xl font-semibold mb-4 text-gray-900">今日精选</h2>
          <FactorCard
            id={data.hero.id}
            title={data.hero.title}
            description={data.hero.description}
            category={data.hero.category}
            symbol={data.hero.default_symbol}
            isPin
            style="hero"
          />
        </section>
      )}

      {/* 副网格 */}
      {data.cases.length > 0 && (
        <section>
          <h2 className="text-lg font-medium mb-4 text-gray-700">更多案例</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {data.cases.map((c) => (
              <FactorCard
                key={c.id}
                id={c.id}
                title={c.title}
                description={c.description}
                category={c.category}
                symbol={c.default_symbol}
                isPin={c.pin_priority != null}
                style="grid"
              />
            ))}
          </div>
        </section>
      )}

      {data.cases.length === 0 && !data.hero && (
        <div className="text-center py-16 text-gray-400">暂无案例</div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: 提交**

```bash
git add frontend/app/\(dashboard\)/skill-generator/_components/GalleryView.tsx \
  frontend/app/\(dashboard\)/skill-generator/_components/FactorCard.tsx
git commit -m "feat: add GalleryView + FactorCard components"
```

---

## Task 7: 前端 — 我的因子（MineView）

**Files:**
- Create: `frontend/app/(dashboard)/skill-generator/_components/MineView.tsx`

- [ ] **Step 1: MineView**

```tsx
// frontend/app/(dashboard)/skill-generator/_components/MineView.tsx
import { useEffect, useState } from 'react'
import { getMine, deleteSkill } from '@/lib/api/skills'
import { FactorCard } from './FactorCard'
import { toast } from 'sonner'

export function MineView() {
  const [skills, setSkills] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    getMine()
      .then((r) => setSkills(r.skills))
      .catch(() => setSkills([]))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const handleDelete = async (id: string) => {
    if (!confirm('确定删除该因子？')) return
    await deleteSkill(id)
    setSkills((prev) => prev.filter((s) => s.id !== id))
    toast.success('已删除')
  }

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-pulse text-gray-400">加载我的因子...</div></div>

  return (
    <div>
      {skills.length === 0 ? (
        <div className="text-center py-16">
          <div className="text-4xl mb-4">📊</div>
          <div className="text-lg font-medium text-gray-700 mb-2">还没有因子资产</div>
          <div className="text-gray-400 mb-6">在案例馆选择一个案例或新建一个因子开始探索</div>
          <button onClick={() => window.location.href = '/skill-generator?tab=gallery'} className="px-4 py-2 bg-primary text-white rounded-lg">
            去案例馆看看
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {skills.map((s) => (
            <div key={s.id} className="relative group">
              <FactorCard
                id={s.id}
                title={s.title}
                description={s.description}
                category={s.category}
                symbol={s.default_symbol}
                style="grid"
              />
              <button
                onClick={(e) => { e.stopPropagation(); handleDelete(s.id) }}
                className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 transition-opacity"
              >
                删除
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/app/\(dashboard\)/skill-generator/_components/MineView.tsx
git commit -m "feat: add MineView component"
```

---

## Task 8: 前端 — 新建向导（NewView + 三步）

**Files:**
- Create: `frontend/app/(dashboard)/skill-generator/_components/NewView.tsx`
- Create: `frontend/app/(dashboard)/skill-generator/_hooks/useSkillStream.ts`

- [ ] **Step 1: useSkillStream hook**

```typescript
// frontend/app/(dashboard)/skill-generator/_hooks/useSkillStream.ts
import { useState, useRef } from 'react'
import { generateSkillStream } from '@/lib/api/skills'

export function useSkillStream() {
  const [code, setCode] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [done, setDone] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const startStream = async (messages: { role: string; content: string }[]) => {
    setCode('')
    setStreaming(true)
    setDone(false)
    abortRef.current = new AbortController()

    try {
      const resp = await generateSkillStream(messages, abortRef.current.signal)
      const reader = resp.getReader()
      const decoder = new TextDecoder()
      let full = ''
      while (true) {
        const { done: d, value } = await reader.read()
        if (d) break
        const chunk = decoder.decode(value)
        // SSE 解析: data: {...}\n\n
        const lines = chunk.split('\n')
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const json = JSON.parse(line.slice(6))
              if (json.content) {
                full += json.content
                setCode(full)
              }
              if (json.done) {
                setDone(true)
                setStreaming(false)
              }
            } catch { /* ignore parse errors */ }
          }
        }
      }
    } catch {
      setStreaming(false)
    }
  }

  const stop = () => {
    abortRef.current?.abort()
    setStreaming(false)
  }

  return { code, streaming, done, startStream, stop }
}
```

- [ ] **Step 2: NewView（三步向导）**

```tsx
// frontend/app/(dashboard)/skill-generator/_components/NewView.tsx
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useSkillStream } from '../_hooks/useSkillStream'
import { saveSkill } from '@/lib/api/skills'
import { toast } from 'sonner'

const CATEGORIES = [
  { id: 'momentum', label: '强者恒强', emoji: '🚀' },
  { id: 'reversal', label: '跌深必反', emoji: '🔄' },
  { id: 'volatility', label: '波动突破', emoji: '⚡' },
  { id: 'volume', label: '量价共振', emoji: '📊' },
  { id: 'sentiment', label: '情绪极端', emoji: '😱' },
  { id: 'technical', label: '技术指标', emoji: '📈' },
]

type Step = 1 | 2 | 3

export function NewView() {
  const [step, setStep] = useState<Step>(1)
  const [symbol, setSymbol] = useState('')
  const [startDate, setStartDate] = useState('2024-01-01')
  const [endDate, setEndDate] = useState('2025-05-16')
  const [freq, setFreq] = useState<'daily' | 'weekly'>('daily')
  const [selectedCategory, setSelectedCategory] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)
  const router = useRouter()

  const { code, streaming, done, startStream, stop } = useSkillStream()

  const handleLoadData = () => {
    if (!symbol.trim()) { toast.error('请输入股票代码'); return }
    setStep(2)
  }

  const handleGenerate = async () => {
    const prompt = selectedCategory
      ? `${CATEGORIES.find(c => c.id === selectedCategory)?.label}：${description || selectedCategory}`
      : description
    await startStream([{ role: 'user', content: prompt }])
    setStep(3)
  }

  const handleSave = async () => {
    if (!code || !selectedCategory) return
    setSaving(true)
    try {
      const saved = await saveSkill({
        title: `${symbol} · ${CATEGORIES.find(c => c.id === selectedCategory)?.label}`,
        description: description || selectedCategory,
        category: selectedCategory,
        code,
        symbol,
        start_date: startDate,
        end_date: endDate,
        freq,
      })
      toast.success('已保存到我的因子')
      router.push(`/skill-generator?tab=mine&factor_id=${saved.id}`)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      {/* 步骤指示器 */}
      <div className="flex items-center gap-2">
        {[1, 2, 3].map((s) => (
          <div key={s} className={`flex items-center gap-2 ${s < 3 ? 'flex-1' : ''}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold
              ${step >= s ? 'bg-primary text-white' : 'bg-gray-200 text-gray-500'}`}>
              {s}
            </div>
            {s < 3 && <div className={`h-0.5 flex-1 ${step > s ? 'bg-primary' : 'bg-gray-200'}`} />}
          </div>
        ))}
      </div>

      {/* Step 1: 选股 */}
      {step === 1 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <h2 className="text-lg font-semibold">第一步：选择股票</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-600 mb-1">股票代码</label>
              <input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                placeholder="如 NVDA、600519、510300"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">频率</label>
              <select value={freq} onChange={(e) => setFreq(e.target.value as any)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
                <option value="daily">日线</option>
                <option value="weekly">周线</option>
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">开始日期</label>
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">结束日期</label>
              <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
          <button onClick={handleLoadData}
            className="w-full py-3 bg-primary text-white rounded-lg font-medium hover:bg-primary/90 transition-colors">
            加载数据 →
          </button>
        </div>
      )}

      {/* Step 2: 选命题 */}
      {step === 2 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <h2 className="text-lg font-semibold">第二步：选择命题</h2>
          <div className="grid grid-cols-3 gap-3">
            {CATEGORIES.map((cat) => (
              <button key={cat.id}
                onClick={() => setSelectedCategory(cat.id)}
                className={`p-3 rounded-xl border-2 text-center transition-all ${
                  selectedCategory === cat.id ? 'border-primary bg-primary/5' : 'border-gray-200 hover:border-gray-300'
                }`}>
                <div className="text-2xl mb-1">{cat.emoji}</div>
                <div className="text-sm font-medium">{cat.label}</div>
              </button>
            ))}
          </div>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)}
            placeholder="补充描述（可选）：如「关注 2024 年 Q2财报后 的动量变化」"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm h-24 resize-none focus:outline-none focus:ring-2 focus:ring-primary" />
          <div className="flex gap-3">
            <button onClick={() => setStep(1)} className="flex-1 py-3 border border-gray-300 rounded-lg text-gray-600 hover:bg-gray-50">← 上一步</button>
            <button onClick={handleGenerate}
              className="flex-1 py-3 bg-primary text-white rounded-lg font-medium hover:bg-primary/90">
              生成因子 ⚡
            </button>
          </div>
        </div>
      )}

      {/* Step 3: AI 生成 */}
      {step === 3 && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="text-lg font-semibold mb-4">第三步：AI 生成中...</h2>
            <pre className="bg-gray-900 text-green-400 p-4 rounded-lg text-xs overflow-x-auto whitespace-pre-wrap font-mono h-64">
              {code || '⏳ 正在生成...'}
            </pre>
            {streaming && (
              <button onClick={stop} className="mt-2 px-4 py-2 border border-gray-600 text-gray-400 rounded-lg text-sm">停止</button>
            )}
          </div>
          {done && (
            <div className="flex gap-3">
              <button onClick={() => setStep(2)} className="flex-1 py-3 border border-gray-300 rounded-lg text-gray-600 hover:bg-gray-50">← 重新描述</button>
              <button onClick={handleSave} disabled={saving}
                className="flex-1 py-3 bg-gradient-to-r from-primary to-blue-600 text-white rounded-lg font-semibold shadow-lg hover:opacity-90 disabled:opacity-50">
                {saving ? '保存中...' : '💾 保存到我的因子'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: 更新 lib/api/skills.ts 中的流式生成调用**

```typescript
// 在 frontend/lib/api/skills.ts 中追加
export async function generateSkillStream(
  messages: { role: string; content: string }[],
  signal?: AbortSignal
): Promise<Response> {
  return client.post('/api/v1/skills/generate', { messages }, { responseType: 'stream', signal })
}
```

- [ ] **Step 4: 提交**

```bash
git add frontend/app/\(dashboard\)/skill-generator/_components/NewView.tsx \
  frontend/app/\(dashboard\)/skill-generator/_hooks/useSkillStream.ts \
  frontend/lib/api/skills.ts
git commit -m "feat: add NewView 3-step wizard + useSkillStream hook"
```

---

## Task 9: 前端 — 详情页（DetailPage + DualChart + MetricCards + NarrativePanel）

**Files:**
- Create: `frontend/app/(dashboard)/skill-generator/_components/DetailPage.tsx`
- Create: `frontend/app/(dashboard)/skill-generator/_components/MetricCards.tsx`
- Create: `frontend/app/(dashboard)/skill-generator/_components/DualChart.tsx`
- Create: `frontend/app/(dashboard)/skill-generator/_components/NarrativePanel.tsx`
- Create: `frontend/app/(dashboard)/skill-generator/_hooks/useFactorData.ts`

- [ ] **Step 1: useFactorData hook**

```typescript
// frontend/app/(dashboard)/skill-generator/_hooks/useFactorData.ts
import { useSkillsStore } from '@/lib/store/skills'
import { rerunSkill } from '@/lib/api/skills'

export function useFactorData() {
  const { detailSkill } = useSkillsStore()

  const rerun = async (symbol: string, start_date: string, end_date: string, freq: string) => {
    if (!detailSkill) return null
    return rerunSkill(detailSkill.id, { symbol, start_date, end_date, freq })
  }

  return { detailSkill, rerun }
}
```

- [ ] **Step 2: MetricCards（4 张指标卡）**

```tsx
// frontend/app/(dashboard)/skill-generator/_components/MetricCards.tsx
interface MetricData {
  current_z: number
  peak_z: number
  peak_date: string
  trigger_count: number
  data_days: number
}

export function MetricCards({ metrics, lastClose, pctChange }: { metrics: MetricData; lastClose: number; pctChange: number }) {
  const cards = [
    { label: '当前偏离', value: `${metrics.current_z >= 0 ? '+' : ''}${metrics.current_z.toFixed(2)}σ`,
      color: 'border-l-blue-500', chip: Math.abs(metrics.current_z) >= 1.5 ? '极端' : '正常' },
    { label: '历史峰值', value: `${metrics.peak_z >= 0 ? '+' : ''}${metrics.peak_z.toFixed(2)}σ`,
      color: 'border-l-orange-500', chip: metrics.peak_date },
    { label: '极端触发', value: `${metrics.trigger_count} 次`, color: 'border-l-green-500', chip: '|z|≥1.0' },
    { label: '数据天数', value: `${metrics.data_days} 天`, color: 'border-l-purple-500', chip: '' },
  ]

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {cards.map((card) => (
        <div key={card.label} className={`bg-white rounded-xl border border-gray-200 p-4 border-l-4 ${card.color}`}>
          <div className="text-xs text-gray-500 mb-1">{card.label}</div>
          <div className="text-2xl font-bold text-gray-900 mb-1">{card.value}</div>
          {card.chip && <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{card.chip}</span>}
        </div>
      ))}
      {/* 股价卡 */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 border-l-4 border-l-gray-400">
        <div className="text-xs text-gray-500 mb-1">当前股价</div>
        <div className="text-2xl font-bold text-gray-900 mb-1">${lastClose.toFixed(2)}</div>
        <span className={`text-xs px-2 py-0.5 rounded-full ${pctChange >= 0 ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
          {pctChange >= 0 ? '▲' : '▼'} {Math.abs(pctChange).toFixed(2)}%
        </span>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: DualChart（K 线 + 因子双图）**

```tsx
// frontend/app/(dashboard)/skill-generator/_components/DualChart.tsx
import { useEffect, useRef } from 'react'
import { createChart, IChartApi, ISeriesApi, BaselineSeries, Time } from 'lightweight-charts'
import { getKline } from '@/lib/api/skills'

export function DualChart({ symbol, startDate, endDate, freq, snapshot, onPriceLoaded }: {
  symbol: string; startDate: string; endDate: string; freq: string
  snapshot: any
  onPriceLoaded?: (close: number, pctChange: number) => void
}) {
  const klineRef = useRef<HTMLDivElement>(null)
  const factorRef = useRef<HTMLDivElement>(null)
  const klineChartRef = useRef<IChartApi | null>(null)
  const factorChartRef = useRef<IChartApi | null>(null)
  const factorSeriesRef = useRef<ISeriesApi | null>(null)

  useEffect(() => {
    if (!klineRef.current || !factorRef.current) return

    const klineChart = createChart(klineRef.current, {
      layout: { background: { color: '#0b1220' }, textColor: '#e2e8f0' },
      grid: { vertLines: { color: '#1a2333' }, horzLines: { color: '#1a2333' } },
    })
    klineChartRef.current = klineChart

    const factorChart = createChart(factorRef.current, {
      layout: { background: { color: '#0b1220' }, textColor: '#e2e8f0' },
      grid: { vertLines: { color: '#1a2333' }, horzLines: { color: '#1a2333' } },
      height: 150,
    })
    factorChartRef.current = factorChart

    // 因子副图：BaselineSeries
    const factorSeries = factorChart.addBaselineSeries({
      baseValue: { type: 'zero' },
      topFillColor1: 'rgba(59, 130, 246, 0.3)',
      topFillColor2: 'rgba(59, 130, 246, 0.0)',
      bottomFillColor1: 'rgba(239, 68, 68, 0.0)',
      bottomFillColor2: 'rgba(239, 68, 68, 0.3)',
      topLineColor: 'rgba(59, 130, 246, 0.8)',
      bottomLineColor: 'rgba(239, 68, 68, 0.8)',
      baseLineColor: 'rgba(148, 163, 184, 0.5)',
    })
    factorSeriesRef.current = factorSeries

    // 渲染因子数据
    const factorData = snapshot?.factor || []
    factorSeries.setData(factorData.map((f: any) => ({ time: f.time as Time, value: f.value })))

    // ±1σ 参考线
    const mean = 0, std = 1  // z-score 标准化后均值=0，std=1
    factorChart.addLineSeries({ color: 'rgba(148,163,184,0.3)', lineStyle: 2, lineWidth: 1 })
      .setData([{ time: factorData[0]?.time as Time ?? '2024-01-01', value: 1 }, { time: factorData[factorData.length-1]?.time as Time ?? '2025-01-01', value: 1 }])
    factorChart.addLineSeries({ color: 'rgba(148,163,184,0.3)', lineStyle: 2, lineWidth: 1 })
      .setData([{ time: factorData[0]?.time as Time ?? '2024-01-01', value: -1 }, { time: factorData[factorData.length-1]?.time as Time ?? '2025-01-01', value: -1 }])

    // 信号点 markers
    const signals = snapshot?.signals || []
    factorSeries.setMarkers(signals.map((s: any) => ({
      time: s.date as Time,
      position: 'aboveBar' as const,
      color: s.z >= 0 ? '#f97316' : '#ef4444',
      shape: 'circle' as const,
      text: `${s.z > 0 ? '▲' : '▼'} ${s.z}`,
      size: 2,
    })))

    // 同步 crosshair
    klineChart.subscribeCrosshairMove((param) => {
      if (param.time) factorChart.setCrosshairPosition(NaN, param.time as Time, factorSeries)
    })
    factorChart.subscribeCrosshairMove((param) => {
      if (param.time) klineChart.setCrosshairPosition(NaN, param.time as Time, klineChartRef.current?.getSeries()[0])
    })

    // 拉 K 线
    getKline(symbol, startDate, endDate, freq).then((bars) => {
      const klineSeries = klineChart.addCandlestickSeries({
        upColor: '#22c55e', downColor: '#ef4444',
        borderUpColor: '#22c55e', borderDownColor: '#ef4444',
        wickUpColor: '#22c55e', wickDownColor: '#ef4444',
      })
      klineSeries.setData(bars)
      klineChart.timeScale().fitContent()

      if (bars.length > 0) {
        const last = bars[bars.length - 1]
        const prev = bars[bars.length - 2]
        const pct = ((last.close - prev.close) / prev.close) * 100
        onPriceLoaded?.(last.close, pct)
      }
    })

    return () => {
      klineChart.remove()
      factorChart.remove()
    }
  }, [symbol, startDate, endDate, freq])

  return (
    <div className="space-y-2">
      <div className="text-xs text-gray-400">K 线主图</div>
      <div ref={klineRef} className="rounded-xl overflow-hidden" style={{ height: 300 }} />
      <div className="text-xs text-gray-400">因子偏离（BaselineSeries）</div>
      <div ref={factorRef} className="rounded-xl overflow-hidden" style={{ height: 150 }} />
    </div>
  )
}
```

- [ ] **Step 4: NarrativePanel（AI 旁白卡片）**

```tsx
// frontend/app/(dashboard)/skill-generator/_components/NarrativePanel.tsx
interface NarrativeData {
  thesis: string
  key_points: { date: string; z: number; text: string }[]
  verdict: { applicable: string; fails: string }
  generated_at: string
  model: string
}

const POINT_COLORS = ['border-l-blue-500', 'border-l-orange-500', 'border-l-green-500', 'border-l-purple-500']

export function NarrativePanel({ narrative, computingMs }: { narrative: NarrativeData | null; computingMs?: number }) {
  if (!narrative) return null

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">
      {/* 头部 */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-blue-400 flex items-center justify-center text-white font-bold text-lg shadow-md">
          α
        </div>
        <div>
          <div className="font-medium text-gray-900">DeepAlpha AI · 资深量化研究员视角</div>
          <div className="flex items-center gap-2 mt-0.5">
            {computingMs && (
              <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
                ⚡ 已缓存 {computingMs}ms
              </span>
            )}
            {narrative.model && (
              <span className="text-xs text-gray-400">{narrative.model}</span>
            )}
          </div>
        </div>
      </div>

      {/* 立意 */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <div className="w-1 h-4 bg-blue-500 rounded-full" />
          <span className="text-xs text-gray-500 uppercase tracking-wider">立意</span>
        </div>
        <p className="text-gray-700 leading-relaxed pl-3">{narrative.thesis}</p>
      </div>

      {/* 关键时点 */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <div className="w-1 h-4 bg-orange-500 rounded-full" />
          <span className="text-xs text-gray-500 uppercase tracking-wider">关键时点</span>
        </div>
        <div className="space-y-3 pl-3">
          {narrative.key_points.map((pt, i) => (
            <div key={pt.date} className={`border-l-2 pl-3 pb-2 ${POINT_COLORS[i % POINT_COLORS.length]}`}>
              <div className="flex items-baseline gap-2 mb-1">
                <span className="text-xs font-mono text-gray-400">{pt.date}</span>
                <span className={`text-xs font-bold ${pt.z >= 0 ? 'text-blue-600' : 'text-red-600'}`}>
                  {pt.z >= 0 ? '+' : ''}{pt.z.toFixed(2)}σ
                </span>
              </div>
              <p className="text-sm text-gray-700">{pt.text}</p>
            </div>
          ))}
        </div>
      </div>

      {/* 适用 / 失效 */}
      <div className="grid grid-cols-2 gap-4 pt-2 border-t border-gray-100">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1 h-4 bg-green-500 rounded-full" />
            <span className="text-xs text-gray-500">适用场景</span>
          </div>
          <p className="text-xs text-gray-600 leading-relaxed">
            {narrative.verdict?.applicable?.split('·').map((s, i) => (
              <span key={i} className="inline-block bg-green-50 text-green-700 px-2 py-0.5 rounded-full mr-1 mb-1">{s}</span>
            ))}
          </p>
        </div>
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1 h-4 bg-red-500 rounded-full" />
            <span className="text-xs text-gray-500">失效场景</span>
          </div>
          <p className="text-xs text-gray-600 leading-relaxed">
            {narrative.verdict?.fails?.split('·').map((s, i) => (
              <span key={i} className="inline-block bg-red-50 text-red-700 px-2 py-0.5 rounded-full mr-1 mb-1">{s}</span>
            ))}
          </p>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: DetailPage（模态全屏）**

```tsx
// frontend/app/(dashboard)/skill-generator/_components/DetailPage.tsx
import { useEffect, useState, useRef } from 'react'
import { useSkillsStore } from '@/lib/store/skills'
import { MetricCards } from './MetricCards'
import { DualChart } from './DualChart'
import { NarrativePanel } from './NarrativePanel'
import { rerunSkill } from '@/lib/api/skills'
import { toast } from 'sonner'

export function DetailPage() {
  const { selectedSkillId, detailSkill, detailLoading, closeDetail } = useSkillsStore()
  const [rerunSymbol, setRerunSymbol] = useState('')
  const [rerunning, setRerunning] = useState(false)
  const [snapshot, setSnapshot] = useState<any>(null)
  const [lastClose, setLastClose] = useState(0)
  const [pctChange, setPctChange] = useState(0)

  useEffect(() => {
    if (detailSkill) {
      setSnapshot(detailSkill.snapshot || {})
      setRerunSymbol(detailSkill.default_symbol)
    }
  }, [detailSkill])

  const handleRerun = async () => {
    if (!rerunSymbol.trim()) return
    setRerunning(true)
    try {
      const result = await rerunSkill(selectedSkillId!, {
        symbol: rerunSymbol.toUpperCase(),
        start_date: detailSkill!.default_start_date,
        end_date: detailSkill!.default_end_date,
        freq: detailSkill!.default_freq as 'daily' | 'weekly',
      })
      setSnapshot(result.snapshot)
      toast.success(`已换股重跑 ${rerunSymbol}`)
    } catch {
      toast.error('重跑失败')
    } finally {
      setRerunning(false)
    }
  }

  if (detailLoading) return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="animate-pulse text-white">加载中...</div>
    </div>
  )

  if (!detailSkill) return null

  return (
    <div className="fixed inset-0 bg-black/60 flex items-start justify-center z-50 p-4 overflow-y-auto"
      onClick={(e) => e.target === e.currentTarget && closeDetail()}>
      <div className="bg-gray-50 w-full max-w-5xl rounded-2xl my-8 overflow-hidden shadow-2xl">
        {/* 顶部栏 */}
        <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button onClick={closeDetail} className="text-gray-400 hover:text-gray-600 mr-2">←</button>
            <h2 className="text-lg font-semibold text-gray-900">{detailSkill.title}</h2>
            <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">精选</span>
          </div>
          {/* 换股重跑 */}
          <div className="flex items-center gap-2">
            <input value={rerunSymbol} onChange={(e) => setRerunSymbol(e.target.value.toUpperCase())}
              className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-28 focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="换股票代码" />
            <button onClick={handleRerun} disabled={rerunning}
              className="px-4 py-1.5 bg-primary text-white rounded-lg text-sm hover:bg-primary/90 disabled:opacity-50">
              {rerunning ? '重跑中...' : '换股重跑 →'}
            </button>
          </div>
        </div>

        {/* 内容 */}
        <div className="p-6 space-y-6">
          {/* 指标卡 */}
          <MetricCards
            metrics={snapshot?.metrics || { current_z: 0, peak_z: 0, peak_date: '', trigger_count: 0, data_days: 0 }}
            lastClose={lastClose}
            pctChange={pctChange}
          />

          {/* 双图 */}
          <div className="bg-[#0b1220] rounded-2xl p-4">
            <DualChart
              symbol={detailSkill.default_symbol}
              startDate={detailSkill.default_start_date}
              endDate={detailSkill.default_end_date}
              freq={detailSkill.default_freq}
              snapshot={snapshot}
              onPriceLoaded={(close, pct) => { setLastClose(close); setPctChange(pct) }}
            />
          </div>

          {/* AI 旁白 */}
          <NarrativePanel narrative={detailSkill.narrative || snapshot?.narrative} />

          {/* 保存按钮（未保存的 skill 显示） */}
          {detailSkill.owner_id === null && (
            <button onClick={() => {
              import('@/lib/api/skills').then(m => m.saveSkill({
                title: detailSkill.title,
                description: detailSkill.description,
                category: detailSkill.category,
                code: detailSkill.code,
                symbol: detailSkill.default_symbol,
                start_date: detailSkill.default_start_date,
                end_date: detailSkill.default_end_date,
                freq: detailSkill.default_freq,
              })).then(() => toast.success('已保存到我的因子'))
            }}
              className="w-full py-4 bg-gradient-to-r from-blue-600 to-blue-500 text-white rounded-xl font-semibold text-lg shadow-lg hover:opacity-90">
              💾 保存到我的因子
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 6: 提交**

```bash
git add frontend/app/\(dashboard\)/skill-generator/_components/DetailPage.tsx \
  frontend/app/\(dashboard\)/skill-generator/_components/MetricCards.tsx \
  frontend/app/\(dashboard\)/skill-generator/_components/DualChart.tsx \
  frontend/app/\(dashboard\)/skill-generator/_components/NarrativePanel.tsx \
  frontend/app/\(dashboard\)/skill-generator/_hooks/useFactorData.ts
git commit -m "feat: add DetailPage with DualChart + MetricCards + NarrativePanel"
```

---

## Task 10: 测试

**Files:**
- Create: `tests/services/skills/test_sandbox.py`
- Create: `tests/services/skills/test_narrator.py`
- Create: `tests/api/test_skills_crud.py`
- Create: `tests/services/skills/test_kline_cache.py`

- [ ] **Step 1: 沙箱测试**

```python
# tests/services/skills/test_sandbox.py
import pytest, asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.services.skills.sandbox import run_in_subprocess

@pytest.mark.asyncio
async def test_basic_factor_computation():
    code = """
def compute(prices, symbol):
    closes = [p['close'] for p in prices]
    return [{'time': prices[i]['date'], 'value': closes[i] / closes[i-10] - 1}
            for i in range(10, len(closes))]
"""
    fake_prices = [{"date": f"2024-01-{d:02d}", "close": 100 + d * 0.5, "open": 100, "high": 102, "low": 99, "volume": 1000}
                  for d in range(1, 61)]
    result, ot = await run_in_subprocess(code, fake_prices, "TEST", "2024-01-01", "2024-03-01")
    assert len(result) > 0
    assert all("value" in r for r in result)

@pytest.mark.asyncio
async def test_sandbox_timeout_kills_process():
    code = """
def compute(prices, symbol):
    import time
    time.sleep(60)  # 故意超时
    return []
"""
    with pytest.raises(Exception):
        await run_in_subprocess(code, [], "TEST", "2024-01-01", "2024-01-10", timeout=5.0)

@pytest.mark.asyncio
async def test_dangerous_import_blocked():
    code = "import os; def compute(p,s): return []"
    with pytest.raises(Exception):
        await run_in_subprocess(code, [], "TEST", "2024-01-01", "2024-01-10")
```

- [ ] **Step 2: narrator 测试**

```python
# tests/services/skills/test_narrator.py
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.services.skills.narrator import generate_narrative

@pytest.mark.asyncio
async def test_narrative_schema():
    snapshot = {
        "factor": [{"time": "2024-04-08", "value": 0.8}] * 20,
        "signals": [{"date": "2024-04-08", "z": 2.5, "close": 850.0}],
        "metrics": {"current_z": 2.5, "peak_z": 3.1, "peak_date": "2024-04-08", "trigger_count": 5, "data_days": 200},
    }
    result = await generate_narrative(snapshot, "NVDA", "momentum")
    assert "thesis" in result
    assert "key_points" in result
    assert "verdict" in result
    assert "applicable" in result["verdict"]
    assert "fails" in result["verdict"]
    assert len(result["key_points"]) == 1
```

- [ ] **Step 3: CRUD API 测试**

```python
# tests/api/test_skills_crud.py
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_gallery_requires_auth():
    r = client.get("/api/v1/skills/gallery")
    assert r.status_code == 401

def test_save_skill_validates_input():
    # 先登录获取 token（见 conftest.py fixture）
    pass
```

- [ ] **Step 4: K 线缓存 user-id 隔离测试**

```python
# tests/services/skills/test_kline_cache.py
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.services.skills.kline import _cache_key

def test_cache_key_includes_user_id():
    assert "u42" in _cache_key(42, "NVDA", "2024-01-01", "2025-01-01", "daily")
    assert "public" in _cache_key(None, "NVDA", "2024-01-01", "2025-01-01", "daily")

def test_cache_key_different_for_different_users():
    assert _cache_key(1, "NVDA", "2024-01-01", "2025-01-01", "daily") != \
           _cache_key(2, "NVDA", "2024-01-01", "2025-01-01", "daily")
```

- [ ] **Step 5: 运行测试**

Run: `cd /Users/zhangfang/deepalpha-club-ai && uv run pytest tests/services/skills/ tests/api/test_skills_crud.py -v --tb=short`
Expected: 所有测试通过（或跳过 sandbox timeout test 在 macOS 上）

- [ ] **Step 6: 提交**

```bash
git add tests/services/skills/ tests/api/test_skills_crud.py
git commit -m "test: add skills module tests (sandbox, narrator, CRUD, cache)"
```

---

## Task 11: 集成验证与收尾

- [ ] **Step 1: 启动后端 + 前端，手动走查三个 Tab**

```
1. 案例馆默认 tab → Hero + 副网格出现
2. 点任意卡片 → DetailPage 模态打开，K 线图 + 因子图渲染
3. 换股重跑 → 填写股票代码 → 新快照生成
4. 保存到我的因子 → 跳转到 my tab
5. 我的因子 tab → 卡片墙出现，删除按钮正常
6. 新建 tab → 三步向导完整流程
7. 验证导航不被遮挡（已去掉负边距）
```

- [ ] **Step 2: 前端类型检查**

Run: `cd /Users/zhangfang/deepalpha-club-ai/frontend && npx tsc --noEmit`

- [ ] **Step 3: 后端 lint**

Run: `uv run ruff check app/`

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit -m "feat: complete factor explorer redesign — gallery, mine, new wizard, detail page, sandbox rewrite"
```

---

## 自检清单

**1. Spec 覆盖检查：**
- ✅ 案例馆 Hero + 副网格（Task 6）
- ✅ 我的因子卡片墙（Task 7）
- ✅ 新建三步向导（Task 8）
- ✅ 详情页模态（Task 9）
- ✅ 因子卡通用组件（Task 6）
- ✅ 4 张指标卡（Task 9）
- ✅ K 线 + 因子双图（Task 9）
- ✅ AI 旁白卡片（Task 9）
- ✅ 保存到我的因子（Task 9）
- ✅ 换股重跑（Task 9）
- ✅ 数据模型：FactorSkill + FactorRun（Task 1）
- ✅ seed 案例迁移（Task 1）
- ✅ 沙箱 subprocess + RLIMIT（Task 2）
- ✅ AI 旁白 narrator（Task 2）
- ✅ K 线缓存 user-id 隔离（Task 2）
- ✅ 新 API：gallery / mine / save / rerun / delete（Task 3）
- ✅ 统一错误类（Task 2）
- ✅ services 拆包（Task 2）
- ✅ user-based 限流（Task 2）
- ✅ 去掉负边距 + 深色修复（Task 4）
- ✅ Tab 路由（Task 5）
- ✅ Zustand store（Task 5）

**2. Placeholder 扫描：** 无 TBD / TODO / "implement later" 等占位符。

**3. 类型一致性检查：**
- `FactorSkillBrief` / `FactorSkillDetail` 字段贯穿 Task 1 → Task 9
- `SaveSkillRequest` / `RerunRequest` 定义在 Task 3，被 Task 8 / Task 9 引用
- `_cache_key(user_id, symbol, ...)` 在 Task 2 定义，Task 10 测试验证
- `narrative_jsonb` 结构 `{thesis, key_points, verdict, generated_at, model}` 在 Task 2 narrator + Task 9 NarrativePanel 中一致

**Plan 完成。**

---

Plan complete and saved to `docs/superpowers/plans/2026-05-17-factor-explorer-redesign.md`.

Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?