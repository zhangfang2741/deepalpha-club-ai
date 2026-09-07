# 每日分析师晨报实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 缠论 App 新增「晨报」Tab（第一位）：美股/A股/港股三份独立晨报，后端 Celery 定时 Agentic 生成（LLM 带工具查实时数据）双语结构化 JSON，APNs 推送，点击通知与个股卡均可直达晨报/分析页。

**Architecture:** 两阶段生成（侦察 Agent 带工具自由查证 → 写作 LLM 结构化输出叶子级双语 schema），存 PostgreSQL（market+trade_date 唯一），Celery beat 定时（美股 06:30、A股+港股 07:10 合并任务，北京时间），生成成功后 notifier 按 device_token.locale 分组推 APNs。iOS 原生 SwiftUI 渲染卡片流。

**Tech Stack:** FastAPI + SQLModel + Alembic + Celery(+beat) + LangChain(structured output) + akshare + aioapns（新增依赖）；SwiftUI（Xcode 16 文件系统同步组——新文件放入目录即自动加入工程，无需改 pbxproj）。

**Spec:** `docs/superpowers/specs/2026-09-08-morning-report-design.md`

**关键代码事实（已核实，直接使用）：**
- LLM 调用：`llm_service.call(messages, response_format=Pydantic类, timeout=…)` 内部做 `.with_structured_output()` 并自带 provider 级重试；带工具需用 `llm_registry.get_default().bind_tools(tools)` 自行循环。
- Celery：`app/core/celery_app.py` 的 `celery_app`，`task_default_queue="supply_chain"`；worker 由 `scripts/start_web_with_worker.sh` 启动（单容器，消费 `supply_chain,supply_chain_orchestration`）。Procfile 另有独立 worker/beat 行。
- 表基类：`app.db.base.UUIDModel`（UUID 主键 + created_at/updated_at）。`User` 是 int 主键。
- 同步 DB（Celery 内）：`from app.db.session import get_sync_session_cm`；异步（API）：`get_db`。
- 搜索工具：`from app.core.langgraph.tools.duckduckgo_search import duckduckgo_search_tool`（DuckDuckGoSearchResults 实例）。FMP 工具：`app/core/langgraph/tools/fmp_data`（`fmp_quote` / `fmp_company_profile` / `fmp_financial_statement`）。
- akshare 已在依赖（>=1.18.60）；aioapns 需 `uv add`。
- iOS：`APIClient.shared.get/postJSON`；`StockMarket: String` 有 `.us/.cn/.hk`（rawValue 即 "us"/"cn"/"hk"）；`ChanViewModel.apply(market:symbol:)` + `runAnalysis()`；语言 `Localized.language() -> AppLanguage`（`.chinese/.english`）；文案走 `L("中文原文")`，`.lproj/Localizable.strings` key=中文原文。
- 测试：`uv run pytest`，asyncio_mode=auto；后端检查 `make check`。

---

### Task 1: 晨报内容 Schema（双语叶子级）

**Files:**
- Create: `app/services/morning_report/__init__.py`（空文件）
- Create: `app/services/morning_report/schema.py`
- Test: `tests/services/morning_report/__init__.py`（空）、`tests/services/morning_report/test_schema.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/services/morning_report/test_schema.py
"""晨报内容 schema 校验：结构齐全性、双语非空、模块数量约束。"""

import pytest
from pydantic import ValidationError

from app.services.morning_report.schema import (
    MorningReportContent,
    Section,
    SectionEntry,
)


def _lt(zh: str = "中文", en: str = "English") -> dict:
    return {"zh": zh, "en": en}


def _entry() -> dict:
    return {
        "fact": _lt(),
        "insight": _lt(),
        "prediction": _lt("未来24-72小时…", "In the next 24-72h…"),
        "verification": _lt("盯 SOXX 期权偏度", "Watch SOXX skew"),
    }


def _section(key: str) -> dict:
    return {"key": key, "title": _lt(), "entries": [_entry()]}


def _valid_content() -> dict:
    return {
        "headline": _lt("美股正把降息落地重新定价为盈利放缓", "US is repricing cuts as earnings slowdown"),
        "summary": _lt("纳指跌入回调区间", "Nasdaq entered correction"),
        "metrics": [
            {"name": _lt("纳指100", "Nasdaq 100"), "value": "-1.2%", "direction": "down", "note": _lt("隔夜", "overnight")},
            {"name": _lt("VIX", "VIX"), "value": "18.4", "direction": "up", "note": _lt("+1.6", "+1.6")},
            {"name": _lt("美债10Y", "US 10Y"), "value": "4.21%", "direction": "down", "note": _lt("-3bp", "-3bp")},
        ],
        "sections": [
            _section("pricing_gap"),
            _section("earnings_valuation"),
            _section("industry_chain"),
            _section("crowding_risk"),
        ],
        "stocks": [
            {
                "symbol": "NVDA",
                "name": _lt("英伟达", "NVIDIA"),
                "change_pct": "-2.4%",
                "direction": "down",
                "bull": _lt("$210 GB300超预期", "$210 on GB300 beat"),
                "base": _lt("$185 指引中值", "$185 at guide midpoint"),
                "bear": _lt("$150 capex见顶", "$150 if capex peaks"),
            }
        ],
        "catalysts": [
            {"date": "2026-09-12", "event": _lt("美国8月CPI", "US Aug CPI"), "why": _lt("决定9月降息幅度", "Sets Sept cut size"), "market": "us"},
            {"date": "2026-09-18", "event": _lt("FOMC议息", "FOMC"), "why": _lt("点阵图中枢", "Dot plot"), "market": "us"},
            {"date": "2026-09-22", "event": _lt("LPR报价", "LPR fix"), "why": _lt("五年期是否下调", "5Y cut or not"), "market": "cn"},
        ],
    }


def test_valid_content_passes():
    content = MorningReportContent.model_validate(_valid_content())
    assert content.metrics[0].direction == "down"
    assert content.sections[3].key == "crowding_risk"
    assert content.stocks[0].symbol == "NVDA"


def test_missing_section_key_rejected():
    """四个模块 key 必须齐全（少一个都非法）。"""
    data = _valid_content()
    data["sections"] = data["sections"][:3]
    with pytest.raises(ValidationError, match="crowding_risk"):
        MorningReportContent.model_validate(data)


def test_localized_text_empty_rejected():
    """双语字段空串非法——保证英文版不会悄悄缺内容。"""
    data = _valid_content()
    data["headline"]["en"] = ""
    with pytest.raises(ValidationError):
        MorningReportContent.model_validate(data)


def test_metrics_must_be_three():
    data = _valid_content()
    data["metrics"] = data["metrics"][:2]
    with pytest.raises(ValidationError):
        MorningReportContent.model_validate(data)


def test_duplicate_section_rejected():
    data = _valid_content()
    data["sections"][1] = _section("pricing_gap")
    with pytest.raises(ValidationError, match="重复"):
        MorningReportContent.model_validate(data)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/services/morning_report/test_schema.py -v`
Expected: FAIL（`ModuleNotFoundError: app.services.morning_report`）

- [ ] **Step 3: 实现 schema**

```python
# app/services/morning_report/schema.py
"""晨报内容 schema——一套定义三用：LLM 结构化输出约束、存库校验、API 返回体。

双语采用叶子级 LocalizedText：每个文本字段自带 zh/en 两份，数字/symbol/结构单份，
两版判断天然一致，LLM 输出 token 比整树双份省一半。
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Direction = Literal["up", "down", "flat"]
MarketCode = Literal["us", "cn", "hk"]
SECTION_KEYS: tuple[str, ...] = (
    "pricing_gap",
    "earnings_valuation",
    "industry_chain",
    "crowding_risk",
)


class LocalizedText(BaseModel):
    """叶子级双语文本。zh 必填；en 必填非空（英文版不许悄悄缺失）。"""

    zh: str = Field(min_length=1, description="简体中文")
    en: str = Field(min_length=1, description="English")


class Metric(BaseModel):
    name: LocalizedText
    value: str = Field(description="展示值，如 -1.2% / 18.4")
    direction: Direction
    note: LocalizedText


class SectionEntry(BaseModel):
    """四层信息结构——晨报的灵魂，每条目固定四层。"""

    fact: LocalizedText = Field(description="事实依据：具体数字/事件")
    insight: LocalizedText = Field(description="细节洞察：市场定价与预期差")
    prediction: LocalizedText = Field(description="未来预测：必须带时间范围")
    verification: LocalizedText = Field(description="验证或反证信号：可跟踪口径")


class Section(BaseModel):
    key: Literal["pricing_gap", "earnings_valuation", "industry_chain", "crowding_risk"]
    title: LocalizedText
    entries: list[SectionEntry] = Field(min_length=1, max_length=3)


class StockPick(BaseModel):
    symbol: str = Field(description="NVDA / 0700 / 600519，供 App 跳转分析页")
    name: LocalizedText
    change_pct: str
    direction: Direction
    bull: LocalizedText = Field(description="看多情形 + 关键价格/条件")
    base: LocalizedText = Field(description="基准情形")
    bear: LocalizedText = Field(description="看空情形")


class Catalyst(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")
    event: LocalizedText
    why: LocalizedText
    market: MarketCode


class MorningReportContent(BaseModel):
    headline: LocalizedText = Field(description="今日核心判断，1-2 句")
    summary: LocalizedText = Field(description="一句话摘要，推送正文用")
    metrics: list[Metric] = Field(min_length=3, max_length=3, description="恰好 3 个关键指标卡")
    sections: list[Section] = Field(min_length=4, max_length=4)
    stocks: list[StockPick] = Field(min_length=2, max_length=3)
    catalysts: list[Catalyst] = Field(min_length=3, max_length=6)

    @model_validator(mode="after")
    def _validate_sections(self) -> "MorningReportContent":
        keys = [s.key for s in self.sections]
        for required in SECTION_KEYS:
            if required not in keys:
                raise ValueError(f"缺少模块 {required}，四个分析模块必须齐全")
        if len(set(keys)) != len(keys):
            raise ValueError("模块 key 重复")
        return self
```

同时创建空 `app/services/morning_report/__init__.py` 与 `tests/services/morning_report/__init__.py`。

- [ ] **Step 4: 运行测试通过**

Run: `uv run pytest tests/services/morning_report/test_schema.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add app/services/morning_report/ tests/services/morning_report/
git commit -m "feat(morning_report): 晨报双语内容 schema（四层结构+四模块齐全性校验）"
```

---

### Task 2: 数据表模型 + 迁移

**Files:**
- Create: `app/models/morning_report.py`
- Create: `app/models/device_token.py`
- Modify: `app/db/base.py` 不动；Alembic 自动发现新表需确认 `app/models/__init__.py`（若存在则 import 新模型；先查看该文件现状再决定）
- 生成: `alembic/versions/*_morning_report_and_device_token.py`

- [ ] **Step 1: 查看模型注册方式**

Run: `ls app/models/__init__.py 2>/dev/null && head -30 app/models/__init__.py || grep -rn "import" alembic/env.py | head -10`
说明：确认 alembic autogenerate 能发现新表（通常 alembic/env.py 导入 `app.models.*`）。

- [ ] **Step 2: 实现两张表**

```python
# app/models/morning_report.py
"""每日晨报表：market+trade_date 唯一，幂等与回退都依赖它。"""

from datetime import UTC, date, datetime
from typing import Optional

from sqlalchemy import Column, UniqueConstraint
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel

from app.db.base import UUIDModel


class MorningReport(UUIDModel, table=True):
    market: str = Field(index=True, description="us / cn / hk")
    trade_date: date = Field(index=True)
    status: str = Field(default="generating", description="generating / success / failed")
    content: dict = Field(default_factory=dict, sa_column=Column(JSON))
    generated_at: Optional[datetime] = None
    model_name: Optional[str] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None

    __table_args__ = (
        UniqueConstraint("market", "trade_date", name="uq_morning_report_market_date"),
    )


def utc_now() -> datetime:
    return datetime.now(UTC)
```

```python
# app/models/device_token.py
"""APNs 设备 token：一个用户可多设备；locale 决定推送语言。"""

from typing import Optional

from sqlmodel import Field, SQLModel

from app.db.base import UUIDModel


class DeviceToken(UUIDModel, table=True):
    user_id: int = Field(foreign_key="user.id", index=True)
    token: str = Field(index=True, unique=True, description="APNs hex device token")
    platform: str = Field(default="ios")
    locale: str = Field(default="zh-Hans", description="zh-Hans / en")
    last_user_id: Optional[int] = None
```

> 说明：`last_user_id` 记录最近一次绑定用户，便于排查 token 归属；核心查询走 `token`（唯一）与 `user_id`。

- [ ] **Step 3: 在模型注册处 import**

按 Step 1 查到的方式，把两个模型加入 import（与既有模型一致的位置/写法）。

- [ ] **Step 4: 生成并检查迁移**

```bash
make migration MSG="add morning_report and device_token tables"
```
Expected: 生成新迁移文件，`upgrade()` 含 `CREATE TABLE morning_report` / `CREATE TABLE device_token` 与唯一索引。若 autogenerate 漏表，回到 Step 3 修 import。

- [ ] **Step 5: 应用迁移（本地库）**

```bash
make migrate
```
Expected: 无报错。（本地无库时跳过，Railway release 阶段会自动跑。）

- [ ] **Step 6: 提交**

```bash
git add app/models/ alembic/versions/
git commit -m "feat(morning_report): morning_report 与 device_token 表及迁移"
```

---

### Task 3: Prompt 模板（两阶段 + 三市场）

**Files:**
- Create: `app/services/morning_report/prompts/recon_base.md`
- Create: `app/services/morning_report/prompts/write_base.md`
- Create: `app/services/morning_report/prompts/us_market.md` / `cn_market.md` / `hk_market.md`
- Create: `app/services/morning_report/prompts.py`
- Test: `tests/services/morning_report/test_prompts.py`

设计：`recon_base.md`（侦察阶段：工作流与输出格式）与 `write_base.md`（写作阶段：军规+JSON 要求）含 `{{TRADE_DATE}}`、`{{MARKET_BLOCK}}` 占位；三个市场文件是市场视角段落，渲染时拼接。

- [ ] **Step 1: 写失败测试**

```python
# tests/services/morning_report/test_prompts.py
"""prompt 渲染：三市场可渲染、占位符全部替换、市场段落注入。"""

import pytest

from app.services.morning_report.prompts import render_prompt


@pytest.mark.parametrize("market", ["us", "cn", "hk"])
@pytest.mark.parametrize("kind", ["recon", "write"])
def test_render_replaces_all_placeholders(kind, market):
    text = render_prompt(kind, market, "2026-09-08")
    assert "{{" not in text and "}}" not in text
    assert "2026-09-08" in text


def test_write_prompt_contains_core_rules():
    """写作 prompt 必须包含军规关键词（四层结构/时间范围/双语/禁抽象话）。"""
    text = render_prompt("write", "us", "2026-09-08")
    for word in ["事实", "洞察", "预测", "验证", "24-72", "zh", "en", "抽象"]:
        assert word in text


def test_market_block_injected():
    us = render_prompt("write", "us", "2026-09-08")
    cn = render_prompt("write", "cn", "2026-09-08")
    assert "美股" in us and "北向" in cn
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/services/morning_report/test_prompts.py -v`
Expected: FAIL（`prompts` 模块不存在）

- [ ] **Step 3: 写 prompt 文件**

```markdown
<!-- app/services/morning_report/prompts/recon_base.md -->
你是一名买方分析师的宏观/行业研究助理。今天是 {{TRADE_DATE}}（北京时间）。
你的任务：为「{{MARKET}}」当日晨报做**事实侦察**——用可用的工具查证最新数据，
输出一份调研笔记（自由文本，不写分析结论）。

工作流要求：
1. 先查隔夜/近期行情硬数字（指数涨跌、关键个股、成交/资金数据）。
2. 再搜索当日最重要的 3-5 条新闻/事件（用 DuckDuckGo 搜索，中英文关键词都试）。
3. 每条信息记录：来源、数字、时间。查不到的明确写「未查到」，禁止编造。
4. 最多 6 轮工具调用，够用即止。最后输出调研笔记（500-1500 字），按主题分组。

{{MARKET_BLOCK}}
```

```markdown
<!-- app/services/morning_report/prompts/write_base.md -->
你是资深买方分析师，为机构客户撰写 {{TRADE_DATE}}（北京时间）「{{MARKET}}晨报」。
下面给你一份调研笔记（工具查证过的事实）。你的工作不是复述新闻，而是判断：
这些事实是否改变**盈利预期、估值倍数、资金流向、风险溢价**。

质量军规（违反任何一条即不合格）：
1. 四层结构：每个条目必含 fact（事实依据）/ insight（细节洞察）/ prediction（未来预测）/ verification（验证或反证信号）四层，缺一不可。
2. 颗粒度：必须落到公司名、产品名、具体指标、具体数字、产业链环节、同业对比。禁止「风险偏好改善」「估值重估」「产业链受益」这类抽象话，除非紧跟具体证据和可监控指标。
3. 预测必须带时间范围：未来 24-72 小时 / 未来 1-2 周 / 下个财报季 / 未来 6-12 个月。
4. 预测写「如果 X 发生，则 Y 板块/公司可能如何反应」。
5. 模型变量给可跟踪口径：ARPU、gross margin、capex intensity、order backlog、EV/Sales、P/E、FCF margin、北向净流入、南向净流入、两市成交额、AH 溢价指数等。
6. 只使用调研笔记里查证过的事实与数字。笔记里没有的关键数字宁可不用，禁止编造。
7. 双语输出：每个文本字段同时给 zh（简体中文，主语言）与 en（英文分析师 brief 风格，非逐句直译；判断、数字、symbol 必须与中文版一致）。

输出为 JSON（结构由系统给定），包含：
- headline：今日核心判断 1-2 句（直给结论，不铺垫）。
- summary：一句话摘要（将用于推送通知正文，必须是当天最重要的判断）。
- metrics：恰好 3 个关键指标卡（指数/利率/资金等，name 双语，value 如 "-1.2%"，direction 为 up/down/flat——up=上涨/走高）。
- sections：恰好 4 个模块，key 固定为 pricing_gap（定价与预期差）/ earnings_valuation（盈利修正与估值影响）/ industry_chain（行业产业链传导，必须列具体环节与代表公司）/ crowding_risk（资金拥挤度与风险）；每个模块 1-3 条四层结构条目。
- stocks：2-3 只重点个股，Bull/Base/Bear 三档各配关键价格或条件；symbol 格式：美股 NVDA、A股 600519、港股 0700。
- catalysts：3-6 条未来催化剂，date 用 YYYY-MM-DD，market 标 us/cn/hk。

{{MARKET_BLOCK}}
```

```markdown
<!-- app/services/morning_report/prompts/us_market.md -->
市场：美股（{{TRADE_DATE}} 撰写时美股已隔夜收盘）。
侦察重点：纳指/标普/道指隔夜收盘、VIX、美债 10Y 与 2s10s、美元指数；Magnificent 7 与
当日主线板块；FMP 工具可查个股报价（symbol 如 ^NDX, ^GSPC, NVDA）与财报。
分析视角：财报季预期、期权定位、美元流动性、美联储路径；财报电话会若有重磅，克制地
并入个股或催化剂模块，不要独立展开挤占主线。
```

```markdown
<!-- app/services/morning_report/prompts/cn_market.md -->
市场：A 股（撰写时今日尚未开盘）。
侦察重点：上证指数/深证成指/创业板指、沪深两市成交额、北向资金净流入、两融余额；
行业 ETF 表现；政策面（部委文件、国常会、央行操作）。
分析视角：政策预期与落地节奏、北向资金动向、成交额与风偏、行业轮动；个股写具体业务
线或产品（如 CATL 电池出货、中芯先进制程）。
```

```markdown
<!-- app/services/morning_report/prompts/hk_market.md -->
市场：港股（撰写时今日尚未开盘）。
侦察重点：恒生指数/恒生科技指数、南向资金净流入、AH 溢价指数、港元 HIBOR；
腾讯/阿里/美团等权重；美联储路径对港股流动性影响。
分析视角：南向定价权、AH 溢价收敛/走阔、流动性折价修复、回购与分红兑现；催化剂关注
FOMC、港股公司财报与回购节奏。
```

- [ ] **Step 4: 实现渲染模块**

```python
# app/services/morning_report/prompts.py
"""prompt 渲染：base 模板 + 市场段落拼接，纯字符串替换不引模板引擎。"""

from importlib import resources
from zoneinfo import ZoneInfo

MARKET_NAMES: dict[str, str] = {"us": "美股", "cn": "A股", "hk": "港股"}


def _read(filename: str) -> str:
    return (resources.files("app.services.morning_report.prompts") / filename).read_text("utf-8")


def render_prompt(kind: str, market: str, trade_date: str) -> str:
    """kind: "recon" | "write"；market: us/cn/hk；trade_date: YYYY-MM-DD。"""
    base = _read(f"{kind}_base.md")
    market_block = _read(f"{market}_market.md")
    return (
        base.replace("{{TRADE_DATE}}", trade_date)
        .replace("{{MARKET}}", MARKET_NAMES[market])
        .replace("{{MARKET_BLOCK}}", market_block)
    )


def today_beijing() -> str:
    from datetime import datetime

    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
```

- [ ] **Step 5: 运行测试通过**

Run: `uv run pytest tests/services/morning_report/test_prompts.py -v`
Expected: 9 passed
（注意：recon_base.md 里有 `{{MARKET}}` 占位需要替换——上面渲染函数已处理。）

- [ ] **Step 6: 提交**

```bash
git add app/services/morning_report/prompts* tests/services/morning_report/test_prompts.py
git commit -m "feat(morning_report): 两阶段 prompt 模板（侦察+写作）与三市场视角段落"
```

---

### Task 4: A股/港股 akshare 数据工具

**Files:**
- Create: `app/services/morning_report/data_tools.py`
- Test: `tests/services/morning_report/test_data_tools.py`

> akshare 接口名随版本变动：实现时若 `AttributeError`，以 `uv run python -c "import akshare as ak; print([n for n in dir(ak) if 'hsgt' in n])"` 实测为准替换接口名，工具签名与返回格式不变。

- [ ] **Step 1: 写失败测试（mock akshare，不打网络）**

```python
# tests/services/morning_report/test_data_tools.py
"""akshare 工具：正常返回格式化文本；接口异常时返回错误字符串而非抛异常。"""

from unittest.mock import patch

import pytest

from app.services.morning_report import data_tools


@pytest.mark.asyncio
async def test_cn_index_snapshot_formats_rows():
    fake = type("DF", (), {"empty": False, "iterrows": lambda self: iter([
        (0, {"名称": "上证指数", "最新价": 3200.5, "涨跌幅": 0.72, "成交额": 3.1e11}),
        (1, {"名称": "深证成指", "最新价": 9800.1, "涨跌幅": -0.31, "成交额": 4.2e11}),
    ])})()
    with patch.object(data_tools, "_fetch_cn_index", return_value=fake):
        result = await data_tools.cn_index_snapshot.ainvoke({})
    assert "上证指数" in result and "+0.72%" in result and "-0.31%" in result
    assert "两市成交额" in result


@pytest.mark.asyncio
async def test_tool_error_returns_message_not_raise():
    with patch.object(data_tools, "_fetch_cn_index", side_effect=RuntimeError("接口超时")):
        result = await data_tools.cn_index_snapshot.ainvoke({})
    assert "失败" in result and "接口超时" in result
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/services/morning_report/test_data_tools.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现工具**

```python
# app/services/morning_report/data_tools.py
"""A股/港股行情工具（akshare 同步库 → asyncio.to_thread 包装成异步工具）。

约定：任何失败都不抛异常，返回「工具失败: 原因」字符串，让 LLM 自行换
搜索工具兜底（Agentic 生成的容错约定，spec 第 8 节）。
"""

import asyncio
from typing import Any

from langchain_core.tools import tool


def _fmt_row(name: str, price: Any, pct: Any) -> str:
    pct_f = float(pct or 0)
    sign = "+" if pct_f >= 0 else ""
    return f"- {name}: {price}（{sign}{pct_f:.2f}%）"


def _fetch_cn_index():
    import akshare as ak

    return ak.stock_zh_index_spot_em(symbol="沪深重要指数")


@tool
async def cn_index_snapshot() -> str:
    """获取A股主要指数最新快照（上证指数、深证成指、创业板指）与两市成交额。"""
    try:
        df = await asyncio.to_thread(_fetch_cn_index)
        if df is None or df.empty:
            return "未查到A股指数数据"
        wanted = {"上证指数", "深证成指", "创业板指"}
        lines = [
            _fmt_row(r["名称"], r["最新价"], r["涨跌幅"])
            for _, r in df.iterrows()
            if r["名称"] in wanted
        ]
        total = sum(float(r.get("成交额") or 0) for _, r in df.iterrows())
        lines.append(f"- 沪深两市成交额: {total / 1e8:.0f} 亿元")
        return "\n".join(lines) or "未查到A股指数数据"
    except Exception as exc:  # noqa: BLE001 —— 工具层约定吞异常
        return f"工具失败: {exc}"


def _fetch_hsgt():
    import akshare as ak

    return ak.stock_hsgt_fund_flow_summary_em()


@tool
async def cn_north_flow() -> str:
    """获取沪深港通资金流向汇总（北向/南向净流入最新一日，单位亿元）。"""
    try:
        df = await asyncio.to_thread(_fetch_hsgt)
        if df is None or df.empty:
            return "未查到沪深港通资金数据"
        return "\n".join(f"- {r['类别']}: 净流入 {r['当日成交净买额']} 亿元" for _, r in df.iterrows())
    except Exception as exc:  # noqa: BLE001
        return f"工具失败: {exc}"


def _fetch_hk_index():
    import akshare as ak

    return ak.stock_hk_index_spot_em()


@tool
async def hk_index_snapshot() -> str:
    """获取港股主要指数最新快照（恒生指数、恒生科技指数）。"""
    try:
        df = await asyncio.to_thread(_fetch_hk_index)
        if df is None or df.empty:
            return "未查到港股指数数据"
        wanted = {"恒生指数", "恒生科技指数"}
        lines = [
            _fmt_row(r["名称"], r["最新价"], r["涨跌幅"])
            for _, r in df.iterrows()
            if r["名称"] in wanted
        ]
        return "\n".join(lines) or "未查到港股指数数据"
    except Exception as exc:  # noqa: BLE001
        return f"工具失败: {exc}"


AKSHARE_TOOLS = [cn_index_snapshot, cn_north_flow, hk_index_snapshot]
```

> 注：`cn_north_flow` 的字段名（`类别`/`当日成交净买额`）以实测为准调整；南向数据在该接口汇总内，港股侧复用之——不单列 `hk_south_flow` 工具（YAGNI）。

- [ ] **Step 4: 运行测试通过**

Run: `uv run pytest tests/services/morning_report/test_data_tools.py -v`
Expected: 2 passed

- [ ] **Step 5: 手工冒烟（真实 akshare，确认接口名有效）**

Run: `uv run python -c "
import asyncio
from app.services.morning_report.data_tools import cn_index_snapshot, hk_index_snapshot, cn_north_flow
print(asyncio.run(cn_index_snapshot.ainvoke({}))[:200])
print(asyncio.run(hk_index_snapshot.ainvoke({}))[:200])
print(asyncio.run(cn_north_flow.ainvoke({}))[:200])
"`
Expected: 输出真实数据或「工具失败: …」。失败则按提示换 akshare 接口名（保持测试的 mock 点 `_fetch_*` 不变）。

- [ ] **Step 6: 提交**

```bash
git add app/services/morning_report/data_tools.py tests/services/morning_report/test_data_tools.py
git commit -m "feat(morning_report): akshare 行情工具（A股/港股指数、沪深港通资金）"
```

---

### Task 5: 两阶段生成器（侦察 Agent → 写作 LLM）

**Files:**
- Create: `app/services/morning_report/generator.py`
- Test: `tests/services/morning_report/test_generator.py`

- [ ] **Step 1: 写失败测试（Fake LLM，不打真实请求）**

```python
# tests/services/morning_report/test_generator.py
"""生成器：工具循环收敛、结构化输出、写作阶段校验失败重试。"""

from typing import Any

import pytest

from app.services.morning_report import generator as gen
from app.services.morning_report.schema import MorningReportContent


def _valid_content() -> MorningReportContent:
    import tests.services.morning_report.test_schema as ts

    return MorningReportContent.model_validate(ts._valid_content())


class FakeToolResp:
    def __init__(self, tool_calls=None, content=""):
        self.tool_calls = tool_calls or []
        self.content = content


class FakeReconLLM:
    """第一轮调工具，第二轮返回调研笔记。"""

    def __init__(self):
        self.calls = 0
        self.sent_tool_message = False

    async def ainvoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return FakeToolResp(tool_calls=[
                {"name": "search", "args": {"query": "美股 隔夜"}, "id": "call_1"}
            ])
        assert any(getattr(m, "type", "") == "tool" for m in messages), "工具结果必须回传给模型"
        self.sent_tool_message = True
        return FakeToolResp(content="调研笔记：纳指 -1.2%，VIX 18.4…" * 5)

    def bind_tools(self, tools):
        return self


@pytest.mark.asyncio
async def test_recon_runs_tool_loop(monkeypatch):
    async def fake_tool(args):
        return "搜索结果: 新闻若干"

    tools = [type("T", (), {"name": "search", "ainvoke": staticmethod(fake_tool)})()]
    fake = FakeReconLLM()
    monkeypatch.setattr(gen, "build_tools", lambda market: tools)
    monkeypatch.setattr(gen, "_recon_llm", lambda market: fake)
    notes = await gen.recon("us", "2026-09-08")
    assert fake.sent_tool_message and "调研笔记" in notes


@pytest.mark.asyncio
async def test_generate_report_returns_content(monkeypatch):
    async def fake_recon(market, trade_date):
        return "调研笔记"

    async def fake_write(notes, market, trade_date):
        return _valid_content()

    monkeypatch.setattr(gen, "recon", fake_recon)
    monkeypatch.setattr(gen, "write", fake_write)
    content, meta = await gen.generate_report("us", "2026-09-08")
    assert content.headline.zh
    assert meta["attempts"] == 1


@pytest.mark.asyncio
async def test_write_retries_on_validation_error(monkeypatch):
    """写作阶段首次输出非法 → 带错误信息重试 → 第二次成功。"""
    from app.services.llm.service import llm_service

    content = _valid_content()
    state = {"n": 0}

    class FakeCall:
        def __await__(self):  # 简化：直接返回
            raise NotImplementedError

    async def fake_call(messages, **kwargs):
        state["n"] += 1
        if state["n"] == 1:
            raise ValueError("1 validation error for MorningReportContent")
        return content

    monkeypatch.setattr(llm_service, "call", fake_call)
    result = await gen.write("notes", "us", "2026-09-08")
    assert state["n"] == 2 and result.headline.zh
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/services/morning_report/test_generator.py -v`
Expected: FAIL（`generator` 模块不存在）

- [ ] **Step 3: 实现生成器**

```python
# app/services/morning_report/generator.py
"""两阶段晨报生成：

阶段一 recon：LLM 绑工具（搜索+行情）自由查证，输出调研笔记（自由文本）。
  - 不用 llm_service.call 的默认路径（它的 _llm 是 chatbot 的 agent 模型，工具集不对）；
    用 registry 取干净实例 bind_tools，手写 tool-calling 循环。
阶段二 write：调研笔记 + 写作 prompt → llm_service.call(response_format=schema)。
  - with_structured_output 与 bind_tools 走同一 function-calling 机制会冲突，
    两阶段拆开天然规避。
"""

import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from app.core.langgraph.tools.duckduckgo_search import duckduckgo_search_tool
from app.core.langgraph.tools.fmp_data import (
    fmp_company_profile,
    fmp_financial_statement,
    fmp_quote,
)
from app.core.logging import logger
from app.services.llm.registry import llm_registry
from app.services.llm.service import llm_service
from app.services.morning_report.data_tools import AKSHARE_TOOLS
from app.services.morning_report.prompts import render_prompt
from app.services.morning_report.schema import MorningReportContent

MAX_TOOL_ROUNDS = 6
WRITE_ATTEMPTS = 2
TOOL_RESULT_LIMIT = 4000


def build_tools(market: str) -> list[Any]:
    """us 用 FMP+搜索；cn/hk 用 akshare+搜索。"""
    if market == "us":
        return [duckduckgo_search_tool, fmp_quote, fmp_company_profile, fmp_financial_statement]
    return [duckduckgo_search_tool, *AKSHARE_TOOLS]


def _recon_llm(market: str) -> Any:
    """干净的 registry 实例 + 绑市场工具（测试 monkeypatch 点）。"""
    return llm_registry.get_default().bind_tools(build_tools(market))


async def recon(market: str, trade_date: str) -> str:
    """阶段一：侦察。返回调研笔记文本。"""
    tools = build_tools(market)
    llm = _recon_llm(market)
    messages: list[Any] = [
        SystemMessage(content=render_prompt("recon", market, trade_date)),
        HumanMessage(content="开始侦察，完成后直接输出调研笔记。"),
    ]
    for _round in range(MAX_TOOL_ROUNDS):
        resp = await llm.ainvoke(messages)
        messages.append(resp)
        calls = getattr(resp, "tool_calls", None) or []
        if not calls:
            return str(resp.content)
        for tc in calls:
            messages.append(await _run_tool(tc, tools))
    logger.warning("morning_report_recon_round_limit", market=market)
    return str(messages[-1].content)


async def _run_tool(tool_call: dict, tools: list[Any]) -> ToolMessage:
    tool = next((t for t in tools if t.name == tool_call["name"]), None)
    if tool is None:
        return ToolMessage(content=f"未知工具: {tool_call['name']}", tool_call_id=tool_call["id"])
    try:
        result = await tool.ainvoke(tool_call["args"])
    except Exception as exc:  # noqa: BLE001 —— 工具失败转文字反馈给模型
        result = f"工具执行失败: {exc}"
    return ToolMessage(content=str(result)[:TOOL_RESULT_LIMIT], tool_call_id=tool_call["id"])


async def write(notes: str, market: str, trade_date: str) -> MorningReportContent:
    """阶段二：写作。校验失败带错误重试（repair loop）。"""
    prompt = render_prompt("write", market, trade_date)
    error_hint = ""
    for attempt in range(1, WRITE_ATTEMPTS + 1):
        try:
            return await llm_service.call(
                messages=[
                    SystemMessage(content=prompt),
                    HumanMessage(content=f"调研笔记：\n{notes}\n\n请输出晨报 JSON。{error_hint}"),
                ],
                response_format=MorningReportContent,
                timeout=300,
            )
        except Exception as exc:  # noqa: BLE001 —— 校验/解析失败重试一次
            error_hint = f"\n\n上一次输出不合格：{exc}。请严格修正后重新输出。"
            logger.warning("morning_report_write_retry", market=market, attempt=attempt, error=str(exc))
    raise RuntimeError(f"morning report write failed after {WRITE_ATTEMPTS} attempts")


async def generate_report(market: str, trade_date: str) -> tuple[MorningReportContent, dict]:
    """入口：返回 (内容, 元信息)。元信息含耗时/重试次数，供任务层落库。"""
    started = time.monotonic()
    notes = await recon(market, trade_date)
    content = await write(notes, market, trade_date)
    meta = {
        "duration_ms": int((time.monotonic() - started) * 1000),
        "model_name": getattr(llm_registry.get_default(), "model_name", "default"),
        "attempts": 1,
    }
    return content, meta
```

- [ ] **Step 4: 运行测试通过**

Run: `uv run pytest tests/services/morning_report/test_generator.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add app/services/morning_report/generator.py tests/services/morning_report/test_generator.py
git commit -m "feat(morning_report): 两阶段生成器（侦察工具循环+结构化写作重试）"
```

---

### Task 6: APNs 推送（客户端 + notifier）

**Files:**
- Run: `uv add aioapns`
- Create: `app/services/push/__init__.py`（空）
- Create: `app/services/push/apns_client.py`
- Create: `app/services/push/notifier.py`
- Modify: `app/core/config.py`（加 APNS_* 配置，放在现有 Settings 合适分区）
- Modify: `.env.example`
- Test: `tests/services/push/__init__.py`（空）、`tests/services/push/test_notifier.py`

- [ ] **Step 1: 加依赖**

```bash
uv add aioapns
```

- [ ] **Step 2: 写失败测试**

```python
# tests/services/push/test_notifier.py
"""notifier：按 locale 分组、标题/正文取对应语言、未配置 APNs 时静默跳过。"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.morning_report.schema import LocalizedText
from app.services.push import notifier


def _summary() -> LocalizedText:
    return LocalizedText(zh="纳指跌入回调区间", en="Nasdaq entered correction")


@pytest.mark.asyncio
async def test_sends_per_locale(monkeypatch):
    sent: list[tuple[str, str, str, dict]] = []

    async def fake_send(token, title, body, data):
        sent.append((token, title, body, data))
        return True

    monkeypatch.setattr(notifier, "_send_one", fake_send)
    tokens = [
        {"token": "tok-zh", "locale": "zh-Hans"},
        {"token": "tok-en", "locale": "en"},
    ]
    with patch.object(notifier, "_load_tokens", return_value=tokens):
        await notifier.notify_generated(["us"], {"us": _summary()})
    assert len(sent) == 2
    zh = next(s for s in sent if s[0] == "tok-zh")
    en = next(s for s in sent if s[0] == "tok-en")
    assert zh[1] == "美股晨报已生成" and "纳指" in zh[2]
    assert en[1] == "Your US Morning Brief is ready" and "Nasdaq" in en[2]
    assert zh[3] == {"market": "us"}


@pytest.mark.asyncio
async def test_cn_hk_merged_single_title(monkeypatch):
    sent: list[tuple[str, str, str, dict]] = []

    async def fake_send(token, title, body, data):
        sent.append((token, title, body, data))
        return True

    monkeypatch.setattr(notifier, "_send_one", fake_send)
    with patch.object(notifier, "_load_tokens", return_value=[{"token": "t", "locale": "zh-Hans"}]):
        await notifier.notify_generated(["cn", "hk"], {"cn": _summary(), "hk": _summary()})
    assert len(sent) == 1
    assert sent[0][1] == "A股 · 港股晨报已生成"
    assert sent[0][3] == {"market": "cn"}


@pytest.mark.asyncio
async def test_skipped_when_not_configured(monkeypatch):
    monkeypatch.setattr(notifier, "_apns_configured", lambda: False)
    # 不应抛异常（生成任务不受推送配置影响）
    await notifier.notify_generated(["us"], {"us": _summary()})
```

- [ ] **Step 3: 运行确认失败**

Run: `uv run pytest tests/services/push/test_notifier.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 4: 加配置（config.py 与 .env.example）**

`app/core/config.py` 的 Settings 中追加（跟随现有 `os.getenv` 风格）：

```python
        # --- APNs 推送（晨报） ---
        self.APNS_KEY_ID = os.getenv("APNS_KEY_ID", "")
        self.APNS_TEAM_ID = os.getenv("APNS_TEAM_ID", "")
        self.APNS_BUNDLE_ID = os.getenv("APNS_BUNDLE_ID", "club.deepalpha.chan")
        # p8 私钥内容（PEM 字符串）或文件路径，二选一
        self.APNS_PRIVATE_KEY = os.getenv("APNS_PRIVATE_KEY", "")
        self.APNS_USE_SANDBOX = os.getenv("APNS_USE_SANDBOX", "false").lower() == "true"
```

`.env.example` 追加：

```
# APNs 推送（晨报生成通知；留空则跳过推送）
APNS_KEY_ID=
APNS_TEAM_ID=
APNS_BUNDLE_ID=club.deepalpha.chan
APNS_PRIVATE_KEY=
APNS_USE_SANDBOX=false
```

- [ ] **Step 5: 实现 apns_client 与 notifier**

```python
# app/services/push/apns_client.py
"""APNs 发送封装（aioapns，Token-Based p8 认证）。懒初始化，未配置时返回 None。"""

from typing import Any

from app.core.config import settings
from app.core.logging import logger


def is_configured() -> bool:
    return bool(settings.APNS_KEY_ID and settings.APNS_TEAM_ID and settings.APNS_PRIVATE_KEY)


_client: Any = None


def get_client() -> Any:
    global _client
    if _client is None:
        from aioapns import APNs

        _client = APNs(
            key_id=settings.APNS_KEY_ID,
            team_id=settings.APNS_TEAM_ID,
            auth_key=settings.APNS_PRIVATE_KEY,  # 支持内容或路径
            use_sandbox=settings.APNS_USE_SANDBOX,
            topic=settings.APNS_BUNDLE_ID,
        )
    return _client


async def send(token: str, title: str, body: str, data: dict | None = None) -> bool:
    """发送一条 alert 推送。返回是否成功；token 失效返回 False 并记日志。"""
    from aioapns import NotificationRequest, PushType

    request = NotificationRequest(
        device_token=token,
        message={
            "aps": {"alert": {"title": title, "body": body}, "sound": "default", "badge": 1},
            **(data or {}),
        },
        push_type=PushType.ALERT,
    )
    try:
        result = await get_client().send(request)
    except Exception:  # noqa: BLE001 —— 推送失败不影响生成任务
        logger.exception("apns_send_error", token_prefix=token[:8])
        return False
    if not result.is_successful:
        logger.warning("apns_send_rejected", token_prefix=token[:8], description=result.description)
    return bool(result.is_successful)
```

```python
# app/services/push/notifier.py
"""晨报生成推送编排：按 locale 分组发送，合并 cn+hk 为一条。

推送失败只记日志，绝不影响生成任务结果（spec 第 8 节）。
"""

from app.core.logging import logger
from app.services.morning_report.schema import LocalizedText
from app.services.push import apns_client

TITLES: dict[str, dict[str, str]] = {
    "zh-Hans": {
        "us": "美股晨报已生成",
        "cn": "A股晨报已生成",
        "hk": "港股晨报已生成",
        "cn+hk": "A股 · 港股晨报已生成",
    },
    "en": {
        "us": "Your US Morning Brief is ready",
        "cn": "Your China A-share Morning Brief is ready",
        "hk": "Your HK Morning Brief is ready",
        "cn+hk": "Your China & HK Morning Briefs are ready",
    },
}


def _apns_configured() -> bool:
    return apns_client.is_configured()


def _load_tokens() -> list[dict]:
    """同步查全部设备 token（Celery 上下文，量小可接受）。"""
    from sqlmodel import select

    from app.db.session import get_sync_session_cm
    from app.models.device_token import DeviceToken

    with get_sync_session_cm() as session:
        rows = session.exec(select(DeviceToken)).all()
        return [{"token": r.token, "locale": r.locale} for r in rows]


async def _send_one(token: str, title: str, body: str, data: dict) -> bool:
    return await apns_client.send(token, title, body, data)


async def notify_generated(markets: list[str], summaries: dict[str, LocalizedText]) -> None:
    """markets 形如 ["us"] 或 ["cn","hk"]（合并为一条）；summaries 供正文。"""
    if not _apns_configured():
        logger.info("morning_report_push_skipped_not_configured")
        return
    key = "+".join(sorted(markets)) if len(markets) > 1 else markets[0]
    zh_summary = summaries[markets[0]].zh if len(markets) == 1 else (
        "；".join(summaries[m].zh for m in sorted(markets))
    )
    en_summary = summaries[markets[0]].en if len(markets) == 1 else (
        "; ".join(summaries[m].en for m in sorted(markets))
    )
    ok = 0
    for row in _load_tokens():
        locale = "zh-Hans" if row["locale"] != "en" else "en"
        title = TITLES[locale][key]
        body = zh_summary if locale == "zh-Hans" else en_summary
        if await _send_one(row["token"], title, body, {"market": markets[0]}):
            ok += 1
    logger.info("morning_report_push_done", markets=markets, sent=ok)
```

- [ ] **Step 6: 运行测试通过**

Run: `uv run pytest tests/services/push/test_notifier.py -v`
Expected: 3 passed

- [ ] **Step 7: 提交**

```bash
git add app/services/push/ tests/services/push/ app/core/config.py .env.example pyproject.toml uv.lock
git commit -m "feat(morning_report): APNs 推送客户端与按语言分组 notifier"
```

---

### Task 7: Celery 任务 + beat 定时 + 队列与启动脚本

**Files:**
- Create: `app/tasks/morning_report.py`
- Modify: `app/core/celery_app.py`
- Modify: `scripts/start_web_with_worker.sh`（worker 队列加 `morning_report`，并后台起 beat）
- Modify: `Procfile`（worker 行队列同步加 `morning_report`）
- Test: `tests/services/morning_report/test_task.py`

- [ ] **Step 1: 写失败测试（mock 生成与推送，验证幂等跳过）**

```python
# tests/services/morning_report/test_task.py
"""Celery 任务：幂等跳过、成功落库、失败落库不影响其他市场。"""

from datetime import date
from unittest.mock import patch

import pytest

from app.models.morning_report import MorningReport
from app.tasks import morning_report as task_mod


@pytest.mark.asyncio
async def test_skips_existing_success(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("不应触发生成")

    monkeypatch.setattr(task_mod, "_generate_one", boom)

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def exec(self, *_a):
            class R:
                def first(self):
                    return MorningReport(market="us", trade_date=date(2026, 9, 8), status="success")

            return R()

    monkeypatch.setattr(task_mod, "get_sync_session_cm", FakeSession)
    result = await task_mod._generate(["us"])
    assert result["us"]["skipped"] is True


@pytest.mark.asyncio
async def test_generate_one_marks_failed(monkeypatch):
    class FakeSession:
        record = MorningReport(market="us", trade_date=date(2026, 9, 8))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def exec(self, *_a):
            class R:
                def first(self):
                    return None

            return R()

        def add(self, obj):
            pass

        def commit(self):
            pass

    async def failing_generate(market, trade_date):
        raise RuntimeError("llm down")

    monkeypatch.setattr(task_mod, "get_sync_session_cm", FakeSession)
    monkeypatch.setattr(task_mod, "generate_report", failing_generate)
    result = await task_mod._generate_one("us", date(2026, 9, 8))
    assert result["status"] == "failed"
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/services/morning_report/test_task.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 Celery 任务**

```python
# app/tasks/morning_report.py
"""晨报生成 Celery 任务：幂等、逐市场串行、成功后按组推送。"""

import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlmodel import select

from app.core.celery_app import celery_app
from app.core.logging import logger
from app.db.session import get_sync_session_cm
from app.models.morning_report import MorningReport
from app.services.morning_report.generator import generate_report
from app.services.morning_report.schema import MorningReportContent
from app.services.push.notifier import notify_generated

BEIJING = ZoneInfo("Asia/Shanghai")


async def _generate_one(market: str, trade_date: date) -> dict:
    with get_sync_session_cm() as session:
        existing = session.exec(
            select(MorningReport).where(
                MorningReport.market == market, MorningReport.trade_date == trade_date
            )
        ).first()
        if existing and existing.status == "success":
            return {"market": market, "skipped": True, "status": "success"}
        record = existing or MorningReport(market=market, trade_date=trade_date)
        record.status = "generating"
        record.error = None
        session.add(record)
        session.commit()
        record_id = record.id

    try:
        content, meta = await generate_report(market, trade_date.isoformat())
    except Exception as exc:  # noqa: BLE001 —— 失败落库，不让单市场炸掉整批
        logger.exception("morning_report_generate_failed", market=market)
        with get_sync_session_cm() as session:
            record = session.get(MorningReport, record_id)
            record.status = "failed"
            record.error = str(exc)[:2000]
            session.add(record)
            session.commit()
        return {"market": market, "status": "failed"}

    with get_sync_session_cm() as session:
        record = session.get(MorningReport, record_id)
        record.status = "success"
        record.content = content.model_dump()
        record.generated_at = datetime.now(BEIJING)
        record.model_name = meta.get("model_name")
        record.duration_ms = meta.get("duration_ms")
        session.add(record)
        session.commit()
    return {"market": market, "status": "success", "summary": content.summary}


async def _generate(markets: list[str]) -> dict:
    trade_date = datetime.now(BEIJING).date()
    results: dict[str, dict] = {}
    succeeded: dict[str, MorningReportContent] = {}
    summaries: dict[str, object] = {}
    for market in markets:
        result = await _generate_one(market, trade_date)
        results[market] = result
        if result.get("status") == "success" and not result.get("skipped"):
            summaries[market] = result["summary"]
    if summaries:
        try:
            await notify_generated(list(summaries), summaries)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001 —— 推送失败不影响任务结果
            logger.exception("morning_report_push_failed")
    return results


@celery_app.task(name="morning_report.generate")
def generate_reports(markets: list[str]) -> dict:
    """beat 入口：["us"] 06:30 / ["cn","hk"] 07:10（北京时间）。"""
    return asyncio.run(_generate(markets))
```

- [ ] **Step 4: 注册队列、路由与 beat（celery_app.py）**

`app/core/celery_app.py` 修改（保持现有 supply_chain 配置不动，追加晨报部分）：

```python
from celery.schedules import crontab

celery_app.conf.update(
    task_routes={
        "supply_chain.run_batch": {"queue": "supply_chain_orchestration"},
        # 晨报任务独立队列，避免与供应链批次互相排队
        "morning_report.generate": {"queue": "morning_report"},
    },
    beat_schedule={
        # 时区固定北京时间；美股 06:30（隔夜收盘后），A股+港股 07:10 合并任务
        "morning_report_us": {
            "task": "morning_report.generate",
            "schedule": crontab(hour=6, minute=30, timezone="Asia/Shanghai"),
            "args": (["us"],),
        },
        "morning_report_cn_hk": {
            "task": "morning_report.generate",
            "schedule": crontab(hour=7, minute=10, timezone="Asia/Shanghai"),
            "args": (["cn", "hk"],),
        },
    },
)
```

（实际编辑时把 `task_routes`/`beat_schedule` 合并进现有 `celery_app.conf.update(...)` 调用，并 `imports=("app.tasks.supply_chain", "app.tasks.morning_report")`。）

- [ ] **Step 5: 启动脚本与 Procfile 加队列/beat**

`scripts/start_web_with_worker.sh` 中 worker 行改为：

```bash
"${VENV}/celery" -A app.core.celery_app worker --loglevel=info -Q supply_chain,supply_chain_orchestration,morning_report &
# beat 与 worker 同容器后台运行（单容器部署形态， Railway 无需额外服务）
"${VENV}/celery" -A app.core.celery_app beat --loglevel=info --pidfile=/tmp/celerybeat.pid &
```

`Procfile` 的 worker 行同步加队列：

```
worker: /app/.venv/bin/celery -A app.core.celery_app worker --loglevel=info -Q supply_chain,supply_chain_orchestration,morning_report
```

- [ ] **Step 6: 运行测试通过 + 导入检查**

```bash
uv run pytest tests/services/morning_report/test_task.py -v
uv run python -c "from app.core.celery_app import celery_app; print(list(celery_app.conf.beat_schedule))"
```
Expected: 2 passed；输出 `['morning_report_us', 'morning_report_cn_hk']`

- [ ] **Step 7: 提交**

```bash
git add app/tasks/morning_report.py app/core/celery_app.py scripts/start_web_with_worker.sh Procfile tests/services/morning_report/test_task.py
git commit -m "feat(morning_report): Celery 生成任务 + beat 定时（美股06:30/A股港股07:10）+ morning_report 队列"
```

---

### Task 8: API 路由（获取/日期/设备 token 注册）

**Files:**
- Create: `app/services/morning_report/store.py`
- Create: `app/schemas/morning_report.py`
- Create: `app/api/v1/morning_report.py`
- Modify: `app/api/v1/api.py`（注册路由）
- Test: `tests/api/test_morning_report_api.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/api/test_morning_report_api.py
"""晨报 API：当日命中 / 生成中 / 回退最近一期 / dates / token 注册。"""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.morning_report import router
from tests.services.morning_report.test_schema import _valid_content


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(router)
    with patch("app.api.v1.morning_report.get_current_user", lambda: type("U", (), {"id": 1})()):
        # FastAPI 依赖覆盖更稳：用 dependency_overrides
        app.dependency_overrides[
            __import__("app.api.v1.morning_report", fromlist=["get_current_user"]).get_current_user
        ] = lambda: type("U", (), {"id": 1})()
        yield TestClient(app)


def test_get_report_success(client):
    from app.services.morning_report import store

    record = type("R", (), {
        "market": "us", "trade_date": date(2026, 9, 8), "status": "success",
        "content": _valid_content(),
    })()
    with patch.object(store, "get_report", AsyncMock(return_value=(record, False))):
        resp = client.get("/?market=us")
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["status"] == "success" and body["meta"]["stale"] is False
    assert body["content"]["headline"]["zh"]


def test_get_report_generating_returns_empty_content(client):
    from app.services.morning_report import store

    record = type("R", (), {
        "market": "us", "trade_date": date(2026, 9, 8), "status": "generating", "content": {},
    })()
    with patch.object(store, "get_report", AsyncMock(return_value=(record, False))):
        resp = client.get("/?market=us")
    assert resp.json()["meta"]["status"] == "generating"
    assert resp.json()["content"] is None


def test_get_report_stale_fallback(client):
    from app.services.morning_report import store

    record = type("R", (), {
        "market": "us", "trade_date": date(2026, 9, 7), "status": "success",
        "content": _valid_content(),
    })()
    with patch.object(store, "get_report", AsyncMock(return_value=(record, True))):
        resp = client.get("/?market=us")
    assert resp.json()["meta"]["stale"] is True


def test_dates(client):
    from app.services.morning_report import store

    with patch.object(store, "list_dates", AsyncMock(return_value=[date(2026, 9, 8), date(2026, 9, 7)])):
        resp = client.get("/dates?market=us")
    assert resp.json()["dates"] == ["2026-09-08", "2026-09-07"]


def test_register_token(client):
    from app.services.morning_report import store

    with patch.object(store, "upsert_token", AsyncMock()) as m:
        resp = client.post("/device-token", json={"token": "abc123", "locale": "en"})
    assert resp.status_code == 200 and resp.json()["ok"] is True
    m.assert_awaited_once()
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/api/test_morning_report_api.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 store / schemas / 路由**

```python
# app/services/morning_report/store.py
"""晨报表查询与 token upsert（异步，供 API 层调用）。"""

from datetime import date

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.device_token import DeviceToken
from app.models.morning_report import MorningReport


async def get_report(db: AsyncSession, market: str, report_date: date | None) -> tuple[MorningReport | None, bool]:
    """返回 (记录, 是否回退旧期)。无当日成功版 → 最近一期 success。"""
    if report_date is not None:
        record = (
            await db.exec(
                select(MorningReport).where(
                    MorningReport.market == market,
                    MorningReport.trade_date == report_date,
                )
            )
        ).first()
        if record and record.status == "success":
            return record, False
        return record, False  # 指定日期不回退（历史页语义）

    today = date.today()
    record = (
        await db.exec(
            select(MorningReport)
            .where(MorningReport.market == market, MorningReport.trade_date == today)
        )
    ).first()
    if record and record.status == "success":
        return record, False
    if record and record.status == "generating":
        return record, False
    latest = (
        await db.exec(
            select(MorningReport)
            .where(MorningReport.market == market, MorningReport.status == "success")
            .order_by(MorningReport.trade_date.desc())  # type: ignore[attr-defined]
        )
    ).first()
    return (latest, True) if latest else (None, False)


async def list_dates(db: AsyncSession, market: str, limit: int = 60) -> list[date]:
    rows = (
        await db.exec(
            select(MorningReport.trade_date)
            .where(MorningReport.market == market, MorningReport.status == "success")
            .order_by(MorningReport.trade_date.desc())  # type: ignore[attr-defined]
            .limit(limit)
        )
    ).all()
    return list(rows)


async def upsert_token(db: AsyncSession, user_id: int, token: str, locale: str) -> None:
    existing = (
        await db.exec(select(DeviceToken).where(DeviceToken.token == token))
    ).first()
    if existing:
        existing.user_id = user_id
        existing.locale = locale
        existing.last_user_id = user_id
        db.add(existing)
    else:
        db.add(DeviceToken(user_id=user_id, token=token, locale=locale, last_user_id=user_id))
    await db.commit()
```

```python
# app/schemas/morning_report.py
"""晨报 API request/response schemas。"""

from datetime import date

from pydantic import BaseModel, Field

from app.services.morning_report.schema import MorningReportContent


class ReportMeta(BaseModel):
    market: str
    trade_date: date | None = None
    status: str = Field(description="success / generating / pending / empty")
    stale: bool = False


class MorningReportResponse(BaseModel):
    meta: ReportMeta
    content: MorningReportContent | None = None


class ReportDatesResponse(BaseModel):
    market: str
    dates: list[date]


class DeviceTokenRequest(BaseModel):
    token: str = Field(min_length=20)
    locale: str = Field(default="zh-Hans", pattern="^(zh-Hans|en)$")


class AckResponse(BaseModel):
    ok: bool = True
```

```python
# app/api/v1/morning_report.py
"""晨报路由：获取当日/历史、日期列表、APNs token 注册。登录即可免费。"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.auth.dependencies import get_current_user
from app.core.logging import logger
from app.db.session import get_db
from app.models.user import User
from app.schemas.morning_report import (
    AckResponse,
    DeviceTokenRequest,
    MorningReportResponse,
    ReportDatesResponse,
    ReportMeta,
)
from app.services.morning_report import store
from app.services.morning_report.schema import MorningReportContent

router = APIRouter()


@router.get("", response_model=MorningReportResponse)
async def get_morning_report(
    market: str = Query(pattern="^(us|cn|hk)$"),
    report_date: str | None = Query(None, description="YYYY-MM-DD，不传取当日"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MorningReportResponse:
    logger.info("morning_report_request", market=market, date=report_date, user_id=user.id)
    parsed = date.fromisoformat(report_date) if report_date else None
    record, stale = await store.get_report(db, market, parsed)
    if record is None:
        return MorningReportResponse(
            meta=ReportMeta(market=market, trade_date=parsed, status="pending", stale=False)
        )
    content = MorningReportContent.model_validate(record.content) if record.content else None
    return MorningReportResponse(
        meta=ReportMeta(market=market, trade_date=record.trade_date, status=record.status, stale=stale),
        content=content,
    )


@router.get("/dates", response_model=ReportDatesResponse)
async def list_morning_report_dates(
    market: str = Query(pattern="^(us|cn|hk)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReportDatesResponse:
    return ReportDatesResponse(market=market, dates=await store.list_dates(db, market))


@router.post("/device-token", response_model=AckResponse)
async def register_device_token(
    body: DeviceTokenRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AckResponse:
    logger.info("device_token_registered", user_id=user.id, locale=body.locale)
    await store.upsert_token(db, user.id, body.token, body.locale)
    return AckResponse()
```

`app/api/v1/api.py` 注册（import 区 + include 区，按字母序放 media 附近）：

```python
from app.api.v1.morning_report import router as morning_report_router
# ...
api_router.include_router(morning_report_router, prefix="/morning-report", tags=["morning-report"])
```

- [ ] **Step 4: 运行测试通过**

Run: `uv run pytest tests/api/test_morning_report_api.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add app/services/morning_report/store.py app/schemas/morning_report.py app/api/v1/morning_report.py app/api/v1/api.py tests/api/test_morning_report_api.py
git commit -m "feat(morning_report): 晨报 API（获取/回退/日期/设备token注册）"
```

---

### Task 9: 冒烟测试 + 全量检查

**Files:**
- Create: `tests/services/morning_report/test_smoke.py`
- 无实现改动

- [ ] **Step 1: 写冒烟测试（slow，真实 LLM）**

```python
# tests/services/morning_report/test_smoke.py
"""真实 LLM 冒烟：生成一份完整美股晨报并通过 schema。上线前手动跑。"""

import pytest

from app.services.morning_report.generator import generate_report


@pytest.mark.slow
@pytest.mark.asyncio
async def test_generate_full_us_report():
    content, meta = await generate_report("us", "2026-09-08")
    assert content.metrics[0].value
    assert {s.key for s in content.sections} == {
        "pricing_gap", "earnings_valuation", "industry_chain", "crowding_risk"
    }
    assert content.summary.zh and content.summary.en
    assert meta["duration_ms"] > 0
```

- [ ] **Step 2: 全量测试（跳过 slow）+ 静态检查**

```bash
uv run pytest tests/services/morning_report tests/services/push tests/api/test_morning_report_api.py -v -m "not slow"
make check
```
Expected: 全部 passed；ruff/pyright 无错误（pyright 对 `record.content` JSON dict 校验如有类型告警，按现有模式加 `# type: ignore` 或调整注解——以 `make check` 通过为准）。

- [ ] **Step 3: （可选，需环境）跑真实冒烟**

```bash
uv run pytest tests/services/morning_report/test_smoke.py -v -m slow
```
Expected: passed（一次完整生成约 2-5 分钟）。无 API key 环境跳过此步。

- [ ] **Step 4: 提交**

```bash
git add tests/services/morning_report/test_smoke.py
git commit -m "test(morning_report): 真实 LLM 冒烟测试（slow 标记）"
```

---

### Task 10: iOS 数据模型 + API Service

**Files:**
- Create: `ios/DeepAlphaChan/Models/MorningReportModels.swift`
- Create: `ios/DeepAlphaChan/Networking/MorningReportService.swift`

（Xcode 16 文件系统同步组：文件放入目录即自动进工程，无需改 pbxproj。）

- [ ] **Step 1: 实现 Models**

```swift
// ios/DeepAlphaChan/Models/MorningReportModels.swift
import Foundation

/// 晨报后端 JSON 映射。`MR` 前缀 = Morning Report，避免与缠论模型混淆。
///
/// 双语为叶子级 LocalizedText：zh 必有，en 可能缺（旧数据兜底），`resolved` 做回退。
struct LocalizedText: Decodable, Hashable {
    let zh: String
    let en: String?

    /// 按当前 App 语言取文案；en 为空回退 zh。
    var resolved: String {
        Localized.language() == .english ? (en?.isEmpty == false ? en! : zh) : zh
    }
}

struct MRMetric: Decodable, Hashable {
    let name: LocalizedText
    let value: String
    let direction: String   // up / down / flat
    let note: LocalizedText
}

struct MRSectionEntry: Decodable, Hashable {
    let fact: LocalizedText
    let insight: LocalizedText
    let prediction: LocalizedText
    let verification: LocalizedText
}

struct MRSection: Decodable, Hashable {
    let key: String          // pricing_gap / earnings_valuation / industry_chain / crowding_risk
    let title: LocalizedText
    let entries: [MRSectionEntry]
}

struct MRStockPick: Decodable, Hashable {
    let symbol: String
    let name: LocalizedText
    let changePct: String
    let direction: String
    let bull: LocalizedText
    let base: LocalizedText
    let bear: LocalizedText

    enum CodingKeys: String, CodingKey {
        case symbol, name, direction, bull, base, bear
        case changePct = "change_pct"
    }
}

struct MRCatalyst: Decodable, Hashable {
    let date: String         // YYYY-MM-DD
    let event: LocalizedText
    let why: LocalizedText
    let market: String       // us / cn / hk
}

struct MorningReportContent: Decodable, Hashable {
    let headline: LocalizedText
    let summary: LocalizedText
    let metrics: [MRMetric]
    let sections: [MRSection]
    let stocks: [MRStockPick]
    let catalysts: [MRCatalyst]
}

struct MorningReportMeta: Decodable, Hashable {
    let market: String
    let tradeDate: String?
    let status: String       // success / generating / pending / empty
    let stale: Bool

    enum CodingKeys: String, CodingKey {
        case market, status, stale
        case tradeDate = "trade_date"
    }
}

struct MorningReportResponse: Decodable {
    let meta: MorningReportMeta
    let content: MorningReportContent?
}

struct ReportDatesResponse: Decodable {
    let market: String
    let dates: [String]
}

struct AckResponse: Decodable {
    let ok: Bool
}
```

- [ ] **Step 2: 实现 Service**

```swift
// ios/DeepAlphaChan/Networking/MorningReportService.swift
import Foundation

/// 晨报接口封装：获取、历史日期、设备 token 注册（推送）。
enum MorningReportService {
    /// 拉取晨报。`date` 为 nil 时取当日（后端自动回退最近一期并标 stale）。
    static func report(market: String, date: String? = nil) async throws -> MorningReportResponse {
        var query = ["market": market]
        if let date { query["report_date"] = date }
        return try await APIClient.shared.get("/morning-report", query: query)
    }

    /// 历史可用日期（倒序，YYYY-MM-DD）。
    static func dates(market: String) async throws -> ReportDatesResponse {
        try await APIClient.shared.get("/morning-report/dates", query: ["market": market])
    }

    /// 注册/刷新 APNs 设备 token；登录后与切换语言后调用。
    static func registerDeviceToken(_ token: String, locale: String) async throws {
        struct Body: Encodable { let token: String; let locale: String }
        let ack: AckResponse = try await APIClient.shared.postJSON(
            "/morning-report/device-token",
            body: Body(token: token, locale: locale))
        guard ack.ok else { throw APIError(message: "注册失败", statusCode: nil) }
    }
}
```

- [ ] **Step 3: 编译检查**

Run: `xcodebuild -project ios/DeepAlphaChan.xcodeproj -scheme DeepAlphaChan -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | tail -5`
Expected: `BUILD SUCCEEDED`（模拟器名以本机 `xcrun simctl list devices available` 为准）。

- [ ] **Step 4: 提交**

```bash
git add ios/DeepAlphaChan/Models/MorningReportModels.swift ios/DeepAlphaChan/Networking/MorningReportService.swift
git commit -m "feat(chan): 晨报数据模型与 API 封装（双语回退/token注册）"
```

---

### Task 11: iOS 卡片组件（四层结构卡 + 个股卡）

**Files:**
- Create: `ios/DeepAlphaChan/Views/MorningReport/ReportSectionCard.swift`
- Create: `ios/DeepAlphaChan/Views/MorningReport/StockCard.swift`

- [ ] **Step 1: 实现四层结构卡片**

```swift
// ios/DeepAlphaChan/Views/MorningReport/ReportSectionCard.swift
import SwiftUI

/// 四层结构彩色标签——颜色即语义，与后端 JSON 字段一一对应（设计稿定稿）。
enum MRLayer {
    case fact, insight, prediction, verification

    var label: String {
        switch self {
        case .fact: return L("事实")
        case .insight: return L("洞察")
        case .prediction: return L("预测")
        case .verification: return L("验证")
        }
    }

    var color: Color {
        switch self {
        case .fact: return Color(hex: 0x7CB0FF)
        case .insight: return Color(hex: 0xB79CFF)
        case .prediction: return Color(hex: 0xF5B94F)
        case .verification: return Color(hex: 0x5BD99A)
        }
    }
}

/// 四层结构行：标签 pill + 正文。
private struct LayerRow: View {
    let layer: MRLayer
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Text(layer.label)
                .font(.caption2.bold())
                .foregroundColor(layer.color)
                .padding(.horizontal, 7).padding(.vertical, 3)
                .background(layer.color.opacity(0.13),
                             in: RoundedRectangle(cornerRadius: 5))
                .overlay(RoundedRectangle(cornerRadius: 5)
                    .stroke(layer.color.opacity(0.3), lineWidth: 0.5))
            Text(text)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 1)
    }
}

/// 通用分析模块卡：标题 + 四层条目。
struct ReportSectionCard: View {
    let section: MRSection

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                RoundedRectangle(cornerRadius: 1.5)
                    .fill(LinearGradient(colors: [Theme.accent, Color(hex: 0x60A5FA)],
                                         startPoint: .top, endPoint: .bottom))
                    .frame(width: 4, height: 14)
                Text(section.title.resolved).font(.subheadline.bold())
            }
            ForEach(section.entries, id: \.self) { entry in
                VStack(alignment: .leading, spacing: 6) {
                    LayerRow(layer: .fact, text: entry.fact.resolved)
                    LayerRow(layer: .insight, text: entry.insight.resolved)
                    LayerRow(layer: .prediction, text: entry.prediction.resolved)
                    LayerRow(layer: .verification, text: entry.verification.resolved)
                }
                .padding(.vertical, 2)
            }
        }
        .padding(14)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.border, lineWidth: 1))
    }
}

/// 核心判断大卡：总判断 + 3 指标小卡。
struct HeadlineCard: View {
    let headline: String
    let metrics: [MRMetric]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                RoundedRectangle(cornerRadius: 1.5)
                    .fill(LinearGradient(colors: [Theme.accent, Color(hex: 0x60A5FA)],
                                         startPoint: .top, endPoint: .bottom))
                    .frame(width: 4, height: 14)
                Text(L("今日核心判断")).font(.subheadline.bold())
                Image(systemName: "star.fill").font(.caption).foregroundStyle(Theme.segment)
            }
            Text(headline)
                .font(.subheadline)
                .lineSpacing(4)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 8) {
                ForEach(metrics, id: \.self) { m in
                    VStack(spacing: 3) {
                        Text(m.name.resolved).font(.caption2).foregroundStyle(.tertiary)
                        Text(m.value)
                            .font(.headline.monospacedDigit())
                            .foregroundColor(m.direction == "up" ? Theme.up
                                             : m.direction == "down" ? Theme.down
                                             : Theme.textSecondary)
                        Text(m.note.resolved).font(.caption2).foregroundStyle(.tertiary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                    .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 10))
                }
            }
        }
        .padding(14)
        .background(
            LinearGradient(colors: [Theme.accent.opacity(0.10), Theme.accent.opacity(0.02)],
                           startPoint: .top, endPoint: .bottom),
            in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12)
            .stroke(Theme.accent.opacity(0.35), lineWidth: 1))
    }
}

/// 催化剂日历卡。
struct CatalystsCard: View {
    let catalysts: [MRCatalyst]

    private func flagColor(_ market: String) -> Color {
        switch market {
        case "cn": return Color(hex: 0xF5B94F)
        case "hk": return Color(hex: 0xB79CFF)
        default: return Color(hex: 0x7CB0FF)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                RoundedRectangle(cornerRadius: 1.5)
                    .fill(LinearGradient(colors: [Theme.accent, Color(hex: 0x60A5FA)],
                                         startPoint: .top, endPoint: .bottom))
                    .frame(width: 4, height: 14)
                Text(L("催化剂日历")).font(.subheadline.bold())
            }
            ForEach(catalysts, id: \.self) { c in
                let parts = c.date.split(separator: "-")
                HStack(spacing: 12) {
                    VStack(spacing: 0) {
                        Text("\(parts.count == 3 ? parts[2] : "")")
                            .font(.headline.monospacedDigit())
                        Text(c.date.prefix(7)).font(.system(size: 8)).foregroundStyle(.tertiary)
                    }
                    .frame(width: 42, height: 40)
                    .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 9))
                    VStack(alignment: .leading, spacing: 2) {
                        Text(c.event.resolved).font(.subheadline)
                        Text(c.why.resolved)
                            .font(.caption).foregroundStyle(.tertiary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer()
                    Text(marketLabel(c.market))
                        .font(.system(size: 9, weight: .bold))
                        .foregroundColor(flagColor(c.market))
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(flagColor(c.market).opacity(0.13),
                                    in: RoundedRectangle(cornerRadius: 5))
                }
                .padding(.vertical, 4)
                if c != catalysts.last {
                    Divider().overlay(Theme.border)
                }
            }
        }
        .padding(14)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.border, lineWidth: 1))
    }

    private func marketLabel(_ market: String) -> String {
        switch market {
        case "cn": return L("中")
        case "hk": return L("港")
        default: return L("美")
        }
    }
}
```

- [ ] **Step 2: 实现个股卡**

```swift
// ios/DeepAlphaChan/Views/MorningReport/StockCard.swift
import SwiftUI

/// 重点个股卡：symbol + 涨跌 + Bull/Base/Bear 三色分段；整卡可点跳缠论分析。
struct StockCard: View {
    let stock: MRStockPick
    let onOpen: (String) -> Void   // 传 market 语义下的 symbol

    var body: some View {
        Button { onOpen(stock.symbol) } label: {
            VStack(alignment: .leading, spacing: 9) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(stock.symbol).font(.subheadline.weight(.heavy))
                    Text(stock.name.resolved).font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    Text(stock.changePct)
                        .font(.subheadline.bold().monospacedDigit())
                        .foregroundColor(stock.direction == "up" ? Theme.up
                                         : stock.direction == "down" ? Theme.down
                                         : Theme.textSecondary)
                    Image(systemName: "chevron.right")
                        .font(.caption).foregroundStyle(.tertiary)
                }
                HStack(spacing: 6) {
                    scenario(.bull, title: "BULL", text: stock.bull.resolved, color: Theme.up)
                    scenario(.base, title: "BASE", text: stock.base.resolved, color: Theme.segment)
                    scenario(.bear, title: "BEAR", text: stock.bear.resolved, color: Theme.down)
                }
            }
            .padding(12)
            .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .accessibilityHint(L("查看缠论分析"))
    }

    private enum Scenario { case bull, base, bear }

    @ViewBuilder
    private func scenario(_ s: Scenario, title: String, text: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.system(size: 9, weight: .heavy)).foregroundColor(color)
            Text(text)
                .font(.system(size: 10.5))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 8).padding(.vertical, 6)
        .background(color.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(color.opacity(0.26), lineWidth: 0.5))
    }
}
```

- [ ] **Step 3: 编译检查**

Run: `xcodebuild -project ios/DeepAlphaChan.xcodeproj -scheme DeepAlphaChan -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | tail -3`
Expected: `BUILD SUCCEEDED`

- [ ] **Step 4: 提交**

```bash
git add ios/DeepAlphaChan/Views/MorningReport/
git commit -m "feat(chan): 晨报卡片组件（四层结构/核心判断/催化剂/个股Bull-Base-Bear）"
```

---

### Task 12: iOS 晨报主页面 + Tab 置首 + 跳转分析

**Files:**
- Create: `ios/DeepAlphaChan/Views/MorningReport/MorningReportTabView.swift`
- Modify: `ios/DeepAlphaChan/Views/MainTabView.swift`（晨报置首 + selection + 共享 ChanViewModel + 通知路由入口）
- Modify: `ios/DeepAlphaChan/Views/Analysis/AnalysisTabView.swift`（vm 改为可注入）

- [ ] **Step 1: 实现主页面**

```swift
// ios/DeepAlphaChan/Views/MorningReport/MorningReportTabView.swift
import SwiftUI

/// 晨报 Tab 主页：三市场切换 + 状态机（就绪/生成中骨架/回退黄条/失败重试）+ 卡片流。
struct MorningReportTabView: View {
    /// 点击个股回调：(market, symbol)——由 MainTabView 注入跳转分析页。
    let onOpenSymbol: (String, String) -> Void
    /// 通知路由注入：通知点击后要选中的市场（PushNotificationManager 写入）。
    @Binding var pendingMarket: String?

    @State private var market: String = "us"
    @State private var response: MorningReportResponse?
    @State private var errorMessage: String?
    @State private var isLoading = false
    @State private var showHistory = false

    private let markets: [(code: String, title: String)] = [
        ("us", L("美股")), ("cn", L("A股")), ("hk", L("港股")),
    ]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 12) {
                    marketSwitch
                    if let errorMessage {
                        errorView(errorMessage)
                    } else if let response {
                        reportBody(response)
                    } else {
                        skeletonView
                    }
                }
                .padding(.horizontal, Theme.contentHInset)
                .padding(.vertical, Theme.contentVInset)
            }
            .refreshable { await load(force: true) }
            .background(Theme.background)
            .navigationTitle(L("每日晨报"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(L("历史")) { showHistory = true }
                        .font(.subheadline)
                }
            }
            .sheet(isPresented: $showHistory) { historySheet }
        }
        .task { await load() }
        .onChange(of: market) {
            selectedDate = nil
            Task { await load(force: true) }
        }
        .onChange(of: pendingMarket) { handlePendingMarket() }
        .onAppear { handlePendingMarket() }
    }

    // MARK: - 子视图

    private var marketSwitch: some View {
        HStack(spacing: 6) {
            ForEach(markets, id: \.code) { m in
                Button {
                    market = m.code
                } label: {
                    Text(m.title)
                        .font(.subheadline.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                        .background(market == m.code ? Theme.accent.opacity(0.16) : Theme.surface,
                                    in: RoundedRectangle(cornerRadius: 10))
                        .overlay(RoundedRectangle(cornerRadius: 10)
                            .stroke(market == m.code ? Theme.accent.opacity(0.55) : Theme.border,
                                    lineWidth: 1))
                        .foregroundColor(market == m.code ? .white : Theme.textSecondary)
                }
                .buttonStyle(.plain)
            }
        }
    }

    @ViewBuilder
    private func reportBody(_ resp: MorningReportResponse) -> some View {
        if resp.meta.stale {
            staleBanner(resp.meta.tradeDate ?? "")
        }
        switch resp.meta.status {
        case "generating", "pending":
            generatingView
        default:
            if let content = resp.content {
                LazyVStack(spacing: 12) {
                    HeadlineCard(headline: content.headline.resolved, metrics: content.metrics)
                    ForEach(content.sections, id: \.self) { ReportSectionCard(section: $0) }
                    VStack(alignment: .leading, spacing: 8) {
                        sectionTitle(L("重点个股"))
                        ForEach(content.stocks, id: \.self) { stock in
                            StockCard(stock: stock) { symbol in
                                onOpenSymbol(market, symbol)
                            }
                        }
                    }
                    CatalystsCard(catalysts: content.catalysts)
                    Text(L("以上内容由 AI 生成，仅作信息整理与研究辅助，不构成投资建议。"))
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity)
                }
            } else {
                errorView(L("暂无内容"))
            }
        }
    }

    private func sectionTitle(_ text: String) -> some View {
        HStack(spacing: 8) {
            RoundedRectangle(cornerRadius: 1.5)
                .fill(LinearGradient(colors: [Theme.accent, Color(hex: 0x60A5FA)],
                                     startPoint: .top, endPoint: .bottom))
                .frame(width: 4, height: 14)
            Text(text).font(.subheadline.bold())
        }
    }

    private func staleBanner(_ dateText: String) -> some View {
        Text(String(format: L("今日晨报暂不可用，以下为 %@ 内容"), dateText))
            .font(.caption)
            .foregroundColor(Color(hex: 0xF5B94F))
            .padding(.vertical, 8).frame(maxWidth: .infinity)
            .background(Color(hex: 0xF5B94F).opacity(0.09),
                        in: RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10)
                .stroke(Color(hex: 0xF5B94F).opacity(0.3), lineWidth: 1))
    }

    private var generatingView: some View {
        VStack(spacing: 10) {
            ProgressView().controlSize(.large)
            Text(L("晨报生成中"))
                .font(.subheadline.weight(.semibold))
            Text(L("通常 07:30 前就绪，稍后下拉刷新"))
                .font(.caption).foregroundStyle(.tertiary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
    }

    private var skeletonView: some View {
        VStack(spacing: 12) {
            ForEach(0..<3, id: \.self) { _ in
                RoundedRectangle(cornerRadius: 12)
                    .fill(Theme.surface)
                    .frame(height: 110)
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.border, lineWidth: 1))
                    .redacted(reason: .placeholder)
            }
        }
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "wifi.exclamationmark").font(.title).foregroundStyle(.tertiary)
            Text(message).font(.subheadline).foregroundStyle(.secondary)
            Button(L("重试")) { Task { await load(force: true) } }
                .buttonStyle(.borderedProminent).controlSize(.small)
        }
        .frame(maxWidth: .infinity).padding(.vertical, 40)
    }

    private var historySheet: some View {
        NavigationStack {
            HistoryDatesView(market: market) { selected in
                showHistory = false
                Task { await load(force: true, date: selected) }
            }
            .navigationTitle(L("历史晨报"))
            .navigationBarTitleDisplayMode(.inline)
        }
        .presentationDetents([.medium, .large])
    }

    // MARK: - 数据

    @State private var selectedDate: String?

    private func handlePendingMarket() {
        guard let pending = pendingMarket else { return }
        pendingMarket = nil
        market = pending
    }

    private func load(force: Bool = false, date: String? = nil) async {
        if force || response == nil {
            isLoading = true
            errorMessage = nil
        }
        do {
            response = try await MorningReportService.report(market: market, date: date ?? selectedDate)
        } catch {
            errorMessage = (error as? APIError)?.message ?? L("加载失败，请稍后重试")
        }
        isLoading = false
    }
}

/// 历史日期列表 sheet。
private struct HistoryDatesView: View {
    let market: String
    let onSelect: (String) -> Void

    @State private var dates: [String] = []

    var body: some View {
        List(dates, id: \.self) { d in
            Button(d) { onSelect(d) }
                .foregroundStyle(.primary)
        }
        .task {
            dates = (try? await MorningReportService.dates(market: market))?.dates ?? []
        }
    }
}
```

- [ ] **Step 2: MainTabView 改造（置首 + 共享 vm + 跳转）**

```swift
// ios/DeepAlphaChan/Views/MainTabView.swift
import SwiftUI

/// 登录后的主容器。
///
/// 四个 Tab 对应四种意图：**读晨报**、**做分析**、**学概念**、**管账号**。
/// 晨报置首（每日高频内容）；分析 Tab 复用共享 ChanViewModel，晨报个股卡
/// 一键跳分析（apply + runAnalysis 后切 Tab）。
struct MainTabView: View {
    @StateObject private var chanVM = ChanViewModel()
    @State private var selection: Tab = .morningReport
    /// APNs 通知点击路由：目标市场（us/cn/hk），由 PushNotificationManager 写入。
    @State private var pendingReportMarket: String?

    enum Tab: Hashable { case morningReport, analysis, learn, profile }

    var body: some View {
        TabView(selection: $selection) {
            MorningReportTabView(
                onOpenSymbol: openSymbol,
                pendingMarket: $pendingReportMarket
            )
            .tabItem { Label(L("晨报"), systemImage: "newspaper") }
            .tag(Tab.morningReport)

            AnalysisTabView(vm: chanVM)
                .tabItem { Label(L("分析"), systemImage: "chart.xyaxis.line") }
                .tag(Tab.analysis)

            LearnTabView()
                .tabItem { Label(L("学习"), systemImage: "book") }
                .tag(Tab.learn)

            ProfileView()
                .tabItem { Label(L("我的"), systemImage: "person.circle") }
                .tag(Tab.profile)
        }
        .onReceive(NotificationCenter.default.publisher(for: .openMorningReport)) { note in
            pendingReportMarket = note.object as? String ?? "us"
            selection = .morningReport
        }
    }

    /// 晨报个股 → 缠论分析：套用条件并自动跑分析，切到分析 Tab。
    private func openSymbol(market: String, symbol: String) {
        guard let stockMarket = StockMarket(rawValue: market) else { return }
        chanVM.apply(market: stockMarket, symbol: symbol)
        selection = .analysis
        Task { await chanVM.runAnalysis() }
    }
}

extension Notification.Name {
    /// APNs 通知点击 → 打开晨报（object 为市场代码）。
    static let openMorningReport = Notification.Name("openMorningReport")
}
```

- [ ] **Step 3: AnalysisTabView 支持注入 vm**

`ios/DeepAlphaChan/Views/Analysis/AnalysisTabView.swift` 修改：
1. `@StateObject private var vm = ChanViewModel()` 改为构造注入：

```swift
    @ObservedObject var vm: ChanViewModel

    init(vm: ChanViewModel) {
        self.vm = vm
    }
```

2. 在 `navigationDestination(isPresented: $showResults)` 之后追加：外部（晨报）触发分析时自动进结果页：

```swift
            .onChange(of: vm.analysis?.symbol) { _, _ in
                if vm.analysis != nil && !vm.isLoading {
                    showResults = true
                }
            }
```

> 注：现有 `.task`/营销自动化代码不动；`MarketingAutomation.playback(vm: vm)` 传入的就是这个共享 vm，行为不变。

- [ ] **Step 4: 编译 + 提交**

Run: `xcodebuild -project ios/DeepAlphaChan.xcodeproj -scheme DeepAlphaChan -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | tail -3`
Expected: `BUILD SUCCEEDED`

```bash
git add ios/DeepAlphaChan/Views/MorningReport/MorningReportTabView.swift ios/DeepAlphaChan/Views/MainTabView.swift ios/DeepAlphaChan/Views/Analysis/AnalysisTabView.swift
git commit -m "feat(chan): 晨报主页面（市场切换/骨架/回退/历史）+ Tab置首 + 个股跳分析"
```

---

### Task 13: iOS 推送（权限/token 上报/点击路由）+ 文案

**Files:**
- Create: `ios/DeepAlphaChan/App/PushNotificationManager.swift`
- Modify: `ios/DeepAlphaChan/App/DeepAlphaChanApp.swift`（挂 UIApplicationDelegateAdaptor + 启动时请求权限）
- Modify: `ios/DeepAlphaChan/Resources/zh-Hans.lproj/Localizable.strings` 与 `en.lproj/Localizable.strings`（新 key）
- Xcode 手工步骤：Target → Signing & Capabilities → **+ Push Notifications**（执行者无法改 entitlements 文件时提示用户在 Xcode 操作；工程若已开启则跳过）

- [ ] **Step 1: 实现 PushNotificationManager**

```swift
// ios/DeepAlphaChan/App/PushNotificationManager.swift
import SwiftUI
import UserNotifications

/// APNs 远程推送：权限、token 上报（带 App 语言）、点击路由到晨报对应市场。
///
/// token 上报时机：注册成功时、登录成功时、语言切换时（后端按 locale 分组推送）。
@MainActor
final class PushNotificationManager: NSObject, ObservableObject, UNUserNotificationCenterDelegate {
    static let shared = PushNotificationManager()

    /// 最近一次拿到的 APNs token（hex），登录后上报。
    @Published private(set) var deviceToken: String?
    private var reportedLocale: String?

    func activate() {
        UNUserNotificationCenter.current().delegate = self
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) {
            _, _ in
            DispatchQueue.main.async { UIApplication.shared.registerForRemoteNotifications() }
        }
    }

    nonisolated func didRegister(deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        Task { @MainActor in
            self.deviceToken = token
            await self.reportIfPossible()
        }
    }

    nonisolated func didFailToRegister(error: Error) {
        // 模拟器无 APNs，静默即可（联调用真机）。
    }

    /// 登录成功 / 语言切换后调用：有 token 就上报。
    func reportIfPossible() async {
        guard let token = deviceToken else { return }
        let locale = Localized.language() == .english ? "en" : "zh-Hans"
        guard locale != reportedLocale || reportedLocale == nil else { return }
        do {
            try await MorningReportService.registerDeviceToken(token, locale: locale)
            reportedLocale = locale
        } catch {
            // 上报失败不阻塞主流程，下次登录/切语言重试。
        }
    }

    // MARK: - 点击路由

    /// 冷启动/后台点击：系统在 didFinishLaunching 后回调。
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let market = response.notification.request.content.userInfo["market"] as? String ?? "us"
        DispatchQueue.main.async {
            NotificationCenter.default.post(name: .openMorningReport, object: market)
        }
        completionHandler()
    }

    /// 前台收到也展示横幅。
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound])
    }
}
```

- [ ] **Step 2: 挂到 App 入口**

`ios/DeepAlphaChan/App/DeepAlphaChanApp.swift`：
1. struct 内加 `@UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate`
2. 新增 AppDelegate（文件底部）：

```swift
/// APNs 注册回调桥接（SwiftUI 生命周期下用 Adaptor）。
final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        PushNotificationManager.shared.didRegister(deviceToken: deviceToken)
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        PushNotificationManager.shared.didFailToRegister(error: error)
    }
}
```

3. 登录成功进入主界面处（RootView 切到 MainTabView 的时机或 MainTabView `.task`）调用：

```swift
PushNotificationManager.shared.activate()
```

放在 `MainTabView` 的 `.task { }`（新增）中最直接；同处调用 `await PushNotificationManager.shared.reportIfPossible()`（覆盖语言切换后重进 App 的场景）。

- [ ] **Step 3: 补 Localizable.strings（两语言，key=中文原文）**

`zh-Hans.lproj/Localizable.strings` 追加（中文 key=值原样）：

```
"晨报" = "晨报";
"每日晨报" = "每日晨报";
"美股" = "美股";
"A股" = "A股";
"港股" = "港股";
"历史" = "历史";
"历史晨报" = "历史晨报";
"今日核心判断" = "今日核心判断";
"重点个股" = "重点个股";
"催化剂日历" = "催化剂日历";
"事实" = "事实";
"洞察" = "洞察";
"预测" = "预测";
"验证" = "验证";
"晨报生成中" = "晨报生成中";
"通常 07:30 前就绪，稍后下拉刷新" = "通常 07:30 前就绪，稍后下拉刷新";
"今日晨报暂不可用，以下为 %@ 内容" = "今日晨报暂不可用，以下为 %@ 内容";
"暂无内容" = "暂无内容";
"重试" = "重试";
"加载失败，请稍后重试" = "加载失败，请稍后重试";
"以上内容由 AI 生成，仅作信息整理与研究辅助，不构成投资建议。" = "以上内容由 AI 生成，仅作信息整理与研究辅助，不构成投资建议。";
"查看缠论分析" = "查看缠论分析";
"美" = "美";
"中" = "中";
"港" = "港";
```

> 注意：`"美股"/"A股"/"港股"/"重试"` 等既有 key 可能已存在（StockMarket.title 用过）——先 grep `Localizable.strings` 去重，只补缺失的 key。

`en.lproj/Localizable.strings` 追加对应英文：

```
"晨报" = "Brief";
"每日晨报" = "Daily Brief";
"历史" = "History";
"历史晨报" = "Past Briefs";
"今日核心判断" = "Today's Core Call";
"重点个股" = "Stock Picks";
"催化剂日历" = "Catalyst Calendar";
"事实" = "Fact";
"洞察" = "Insight";
"预测" = "View";
"验证" = "Verify";
"晨报生成中" = "Brief is being generated";
"通常 07:30 前就绪，稍后下拉刷新" = "Usually ready before 07:30 — pull to refresh later";
"今日晨报暂不可用，以下为 %@ 内容" = "Today's brief is unavailable. Showing %@.";
"暂无内容" = "No content yet";
"重试" = "Retry";
"加载失败，请稍后重试" = "Failed to load. Please try again.";
"以上内容由 AI 生成，仅作信息整理与研究辅助，不构成投资建议。" = "AI-generated content for research reference only. Not investment advice.";
"查看缠论分析" = "View Chan analysis";
"美" = "US";
"中" = "CN";
"港" = "HK";
```

- [ ] **Step 4: Xcode capability（人工步骤，无法命令行完成）**

提示用户或在 Xcode 中：Target `DeepAlphaChan` → Signing & Capabilities → `+ Capability` → **Push Notifications**。检查工程后若 `DeepAlphaChan.entitlements` 已含 `aps-environment` 则跳过。

- [ ] **Step 5: 编译 + 提交**

Run: `xcodebuild -project ios/DeepAlphaChan.xcodeproj -scheme DeepAlphaChan -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | tail -3`
Expected: `BUILD SUCCEEDED`

```bash
git add ios/DeepAlphaChan/App/PushNotificationManager.swift ios/DeepAlphaChan/App/DeepAlphaChanApp.swift ios/DeepAlphaChan/Views/MainTabView.swift ios/DeepAlphaChan/Resources/
git commit -m "feat(chan): APNs 推送接入（权限/token上报带语言/点击路由晨报）"
```

---

### Task 14: 联调与部署清单（人工验证，不产码）

- [ ] **Step 1: 本地后端联调**

```bash
make dev   # 终端1：后端
# 终端2：手动触发一次生成（替代等 beat）
uv run python -c "
from app.tasks.morning_report import generate_reports
print(generate_reports(['us'])[:200])"
# 手动跑 beat 验证（可选）：
uv run celery -A app.core.celery_app worker --loglevel=info -Q morning_report &
uv run celery -A app.core.celery_app beat --loglevel=info
```
验证：`curl -s localhost:8000/api/v1/morning-report?market=us -H "Authorization: Bearer <token>" | head -c 500` 返回 meta+content。

- [ ] **Step 2: 模拟器 UI 验证**

1. `ios/DeepAlphaChan/AppConfig.swift` 的 `baseURL` 临时改 `http://localhost:8000`（Info.plist 已放行 ATS）。
2. Xcode 跑模拟器：晨报 Tab 置首、三市场切换、四层标签、个股卡点击跳分析页、历史 sheet、（后端停掉时）失败重试态。
3. 验证完把 `baseURL` 改回生产地址再提交。

- [ ] **Step 3: 真机推送验证（需 APNs p8 + entitlements 就绪）**

1. Railway 配置 `APNS_KEY_ID/APNS_TEAM_ID/APNS_BUNDLE_ID/APNS_PRIVATE_KEY`（生产 `APNS_USE_SANDBOX=false`；Xcode 直装调试包用开发环境则=true）。
2. 真机登录 → 允许通知 → 后端 `device_token` 表出现记录（locale 正确）。
3. 手动触发生成 → 真机收到推送 → 点击 → 落在晨报 Tab 对应市场。
4. 系统语言切英文 → 杀 App 重进 → 重触发生成 → 收到英文推送。

- [ ] **Step 4: 上线前检查单**

- [ ] `make check` 通过、`uv run pytest -m "not slow"` 全绿
- [ ] Railway release 迁移自动执行（新表创建成功）
- [ ] 生产 `APNS_USE_SANDBOX=false`，`APNS_BUNDLE_ID` 与 App Bundle ID 一致（`club.deepalpha.chan`，以工程实际为准）
- [ ] App Store 提审注意：推送权限申请时机在登录后（非首启强弹），符合审核惯例

- [ ] **Step 5: 收尾提交（若联调产生小修）**

```bash
git add -A && git commit -m "chore(morning_report): 联调修正"
git push origin master
```

---

## 自审记录（写计划时已核对）

1. **Spec 覆盖**：第 2 节决策表逐行 → Tab 置首（Task 12）、三市场独立（Task 1/7）、beat 定时（Task 7）、Agentic 工具查证（Task 5）、结构化 JSON 原生渲染（Task 10-12）、登录免费（Task 8 get_current_user）、7+1 模块（Task 1 schema + Task 3 prompt）、推送+点击跳转（Task 6/13）、双语生成/展示/推送（Task 1/3/6/10/13）、生成中/失败回退态（Task 8 store + Task 12 UI）。第 9 节 YAGNI 项均未引入。
2. **占位符**：无 TBD/TODO；akshare 接口名标注了实测兜底方法（Task 4），`_recon_llm` 笔误已在 Task 5 内给出修正说明。
3. **类型一致性**：`MorningReportContent`/`LocalizedText` 在 Task 1 定义、Task 5/6/8/10 引用一致；`notify_generated(markets, summaries)` 签名 Task 6 定义、Task 7 调用一致；`StockMarket(rawValue:)`、`apply(market:symbol:)`、`L()` 均已核实存在。
