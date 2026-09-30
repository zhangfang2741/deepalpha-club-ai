# 量化研究后端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现设计文档 `docs/superpowers/specs/2026-09-30-quant-research-design.md` 的后端部分：美股量化研究计算引擎、全局 FMP 限流器、数据表、夜间批量、`/quant-research` API，以及 A 股一致预期快照落库。

**Architecture:** 纯函数引擎（`app/services/quant_research/` 下 grading / metrics / scoring / stage / revisions / copy，无 IO，单测覆盖）+ 编排层（FMP 拉取经 Redis 令牌桶限流、夜间批量写 Postgres、按需计算样本外股票）+ 薄 API 层。所有估值倍数、利润率、回报率用报表原始值**自己算**（不用 FMP ratios 端点），这样每个指标都能给出带真实数字的算式。

**Tech Stack:** Python 3.13 / FastAPI / SQLModel + asyncpg / redis-py asyncio / httpx / pandas（成分表解析）/ akshare（A 股预期）/ pytest

**配套计划：** 分析师评级接口（`2026-09-30-analyst-rating-api.md`）、iOS 界面（`2026-09-30-quant-research-ios.md`），在本计划完成后编写执行。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `app/services/quant_research/__init__.py` | 包说明 |
| `app/services/quant_research/grading.py` | 13 档分档、百分位、防抖动 |
| `app/services/quant_research/inputs.py` | `StockInputs` 数据类 + 从 FMP JSON 解析（TTM、财年实际、NTM 预期） |
| `app/services/quant_research/metrics.py` | 指标注册表 `METRICS`（维度 / 组 / 方向 / 名称 / 描述）+ `compute_metrics(inputs)` → 原始值、状态、算式输入 |
| `app/services/quant_research/revisions.py` | EPS 修正指标（依赖快照序列） |
| `app/services/quant_research/stage.py` | Dickinson 阶段判定 |
| `app/services/quant_research/scoring.py` | 板块分布、指标打分、维度聚合、综合分与一票否决、关键事实 |
| `app/services/quant_research/copy.py` | zh / en 文案模板 + 禁用词表 |
| `app/services/quant_research/universe.py` | 标普1500 成分（维基）、GICS 板块键、FMP sector 映射 |
| `app/services/quant_research/fmp.py` | FMP 拉取（经限流器） |
| `app/services/quant_research/repository.py` | 4 张表的读写（异步会话） |
| `app/services/quant_research/builder.py` | 把一只股票的打分结果组装成响应 schema |
| `app/services/quant_research/batch.py` | 夜间批量编排 + A 股预期快照 |
| `app/services/quant_research/service.py` | 请求入口：读当日结果 / 样本外现算 / 缓存 |
| `app/services/quant_research/scheduler.py` | 夜间触发循环 |
| `app/cache/fmp_budget.py` | Redis 令牌桶 + 熔断 |
| `app/models/quant_research.py` | 4 张表模型 |
| `app/schemas/quant_research.py` | 响应 schema |
| `app/api/v1/quant_research.py` | 路由 |
| `scripts/quant_seed_import.py` | 2026-09-30 首份预期快照导入 |
| `tests/services/quant_research/*` | 单测 + golden |
| `tests/fixtures/quant_research/*` | NVDA / JPM / O / XOM 原始数据 |

---

### Task 1: 分档与防抖动（grading.py）

**Files:** Create `app/services/quant_research/__init__.py`, `app/services/quant_research/grading.py`; Test `tests/services/quant_research/__init__.py`, `tests/services/quant_research/test_grading.py`

- [ ] **Step 1: 写失败测试**

```python
from app.services.quant_research.grading import BANDS, grade_for, grade_with_hysteresis, percentile_of

def test_bands_edges():
    assert grade_for(93) == "A+" and grade_for(92.99) == "A"
    assert grade_for(20) == "D-" and grade_for(19.99) == "F"
    assert grade_for(0) == "F" and grade_for(100) == "A+"
    assert [g for _, g in BANDS][:3] == ["A+", "A", "A-"]

def test_hysteresis_keeps_previous_within_margin():
    # 旧等级 B（66~73），今天 64.5：越界 1.5 < 2 → 仍 B
    assert grade_with_hysteresis(64.5, "B") == "B"
    # 越界 2 及以上才改
    assert grade_with_hysteresis(64.0, "B") == "B-"
    assert grade_with_hysteresis(75.5, "B") == "B+"
    assert grade_with_hysteresis(74.9, "B") == "B"
    assert grade_with_hysteresis(50, None) == "C"

def test_percentile_higher_better_and_lower_better():
    values = [1, 2, 3, 4, 5]
    assert percentile_of(5, values, lower_better=False) == 100.0
    assert percentile_of(1, values, lower_better=True) == 100.0
    assert percentile_of(3, values, lower_better=False) == 60.0  # 小于等于 3 的占 3/5

def test_percentile_ties_and_out_of_sample():
    assert percentile_of(2, [2, 2, 2, 2], lower_better=False) == 100.0
    assert percentile_of(10, [1, 2, 3], lower_better=False) == 100.0   # 样本外更好
    assert percentile_of(0, [1, 2, 3], lower_better=False) == 0.0
```

- [ ] **Step 2:** `uv run pytest tests/services/quant_research/test_grading.py -v` → FAIL（模块不存在）
- [ ] **Step 3: 实现**

```python
"""13 档字母等级（全模块同一把尺子）、板块百分位、防抖动。纯函数。"""
from __future__ import annotations
from bisect import bisect_left, bisect_right

BANDS: list[tuple[float, str]] = [
    (93, "A+"), (86, "A"), (80, "A-"), (73, "B+"), (66, "B"), (60, "B-"),
    (53, "C+"), (46, "C"), (40, "C-"), (33, "D+"), (26, "D"), (20, "D-"), (0, "F"),
]
HYSTERESIS = 2.0
_LOWER = {g: lo for lo, g in BANDS}
_UPPER = {g: (BANDS[i - 1][0] if i else 100.0) for i, (_, g) in enumerate(BANDS)}

def grade_for(p: float) -> str:
    return next(g for lo, g in BANDS if p >= lo)

def grade_with_hysteresis(p: float, prev: str | None) -> str:
    """旧等级区间向两侧各放宽 HYSTERESIS 分；仍在放宽区间内则沿用旧等级。"""
    if prev is None or prev not in _LOWER:
        return grade_for(p)
    lo, hi = _LOWER[prev], _UPPER[prev]
    if lo - HYSTERESIS < p < hi + HYSTERESIS:
        return prev
    return grade_for(p)

def percentile_of(value: float, sorted_values: list[float], *, lower_better: bool) -> float:
    """value 在 sorted_values（升序）中的百分位 0~100，方向统一为越高越好。
    越高越好：不大于它的比例；越低越好：不小于它的比例。"""
    n = len(sorted_values)
    if n == 0:
        return 50.0
    if lower_better:
        return round((n - bisect_left(sorted_values, value)) / n * 100, 1)
    return round(bisect_right(sorted_values, value) / n * 100, 1)
```

注意 `grade_with_hysteresis(64.0,"B")`：B 区间 [66,73)，放宽为 (64,75)，64.0 不在内 → B-；`75.5` → B+；`74.9` → 仍 B。

- [ ] **Step 4:** 测试通过
- [ ] **Step 5:** `git commit -m "feat(quant): 等级分档、板块百分位与防抖动"`

---

### Task 2: 输入解析（inputs.py）

**Files:** Create `app/services/quant_research/inputs.py`; Test `tests/services/quant_research/test_inputs.py`; Fixtures `tests/fixtures/quant_research/{NVDA,JPM,O,XOM}.{isq,est,px}.json`（从 `data/quant_seed/2026-09-30/raw/` 拷贝）+ 用 Task 8 的 fmp 拉取补 `cfq`（现金流 8 季）/`bsq`（资产负债 1 季）/`profile`（4 只各 3 次调用）

`StockInputs`（dataclass，frozen）字段：`symbol, as_of: date, price: float|None, price_date: str|None, closes: list[float]`（升序）、`quarters_income: list[dict]`（新→旧）、`quarters_cash: list[dict]`、`balance: dict|None`、`estimates: list[dict]`（按 date 升序）、`shares_diluted: float|None`（最新季度 `weightedAverageShsOutDil`）、`sector_key: str`。

解析函数（纯函数）：
- `ttm(quarters, key, offset=0) -> float|None`：连续 4 季求和，任一缺失返回 None。
- `fiscal_year_actual(quarters, key) -> tuple[str, float]|None`：按 `fiscalYear` 分组，取最近一个**凑齐 Q1~Q4** 的财年求和（NVDA 2026-09-30 → FY2026）。
- `forward_entries(estimates, as_of) -> (fy1, fy2)`：`date > as_of` 的前两条。
- `ntm(fy1, fy2, key, as_of) -> float|None`：`w = 剩余天数(fy1.date - as_of)/365`（截到 [0,1]），`NTM = w*fy1[key] + (1-w)*fy2[key]`；fy2 缺失时返回 fy1 值。
- `analyst_count(fy1) -> int`：`numAnalystsEps`，缺失为 0。

测试要点：NVDA fixture 上 `fiscal_year_actual(isq,"revenue")[0] == "2026"`；`ntm` 在 fy1 剩 30% 时权重正确（构造 2 条估计手算）；`ttm` 缺季返回 None。

- [ ] Step 1 写测试 → Step 2 FAIL → Step 3 实现 → Step 4 PASS → Step 5 `git commit -m "feat(quant): 报表 TTM / 财年实际 / NTM 预期解析"`

---

### Task 3: 指标注册表与计算（metrics.py）

**Files:** Create `app/services/quant_research/metrics.py`; Test `tests/services/quant_research/test_metrics.py`

`MetricDef`（dataclass）：`key, dimension（valuation|growth|profitability|momentum|revisions）, group, direction（lower_better|higher_better）, name_zh, name_en, desc_zh, desc_en`。`METRICS: dict[str, MetricDef]` 按设计 §3.6 共 36 项（估值 14：pe_ttm/pe_fwd/peg_ttm/peg_fwd/ps_ttm/ps_fwd/ev_sales_ttm/ev_sales_fwd/ev_ebitda_ttm/ev_ebitda_fwd/ev_ebit_ttm/ev_ebit_fwd/pb/pcf；成长 9：rev_yoy/rev_fwd/rev_cagr3/ebitda_yoy/ebitda_fwd/ebit_yoy/ebit_fwd/eps_yoy/eps_fwd；盈利 9：gross_m/ebit_m/ebitda_m/net_m/fcf_m/roe/roa/roic/asset_turn；动量 4：r3m/r6m/r9m/r12m；修正 4 在 Task 4）。

`MetricValue`（dataclass）：`value: float|None, status: Literal["ok","not_meaningful","not_applicable","missing"], inputs: list[tuple[str, float|None]]`（算式用，如 `[("股价",227.21),("NTM EPS 预期",5.51)]`）, `op: str`（`"div"` / `"growth"` / `"cagr3"` / `"ret"`，文案层据此拼算式）。

`compute_metrics(inp: StockInputs) -> dict[str, MetricValue]` 规则：
- 市值 = price × shares_diluted；EV = 市值 + totalDebt − cashAndShortTermInvestments。
- **倍数**（`_multiple(num, den, *, negative_den_status)`）：num 或 den 为 None → missing；den ≤ 0 → `negative_den_status`；num ≤ 0 → not_meaningful。
  - 利润类分母（EPS、EBITDA、EBIT、经营现金流）≤ 0 → `not_meaningful`（亏损，按最差）。
  - 净资产 ≤ 0 的 P/B → `not_applicable`（回购导致，不参与）。
- PEG TTM = PE TTM / (EPS 同比 × 100)；PEG 前瞻 = PE 前瞻 / ((FY2 EPS / FY1 EPS − 1) × 100)；增速 ≤ 0 → not_meaningful。
- 预期类（*_fwd、peg_fwd）在 `analyst_count(fy1) < 3` 时 → missing。
- 增长 `_growth(cur, base)`：base ≤ 0 或缺失 → missing；前瞻增速 = FY1 预期 / 上一完整财年实际 − 1。3 年复合 = (TTM / 12 季前 TTM)^(1/3) − 1。
- 利润率 = TTM 项 / TTM 营收；FCF = TTM 经营现金流 + TTM capex（capex 为负）。
- ROE = TTM 净利 / 股东权益；权益 ≤ 0 → not_applicable（同 P/B）。ROA = 净利 / 总资产；ROIC = EBIT×(1−有效税率) / (totalDebt + 权益 − 现金)，有效税率 = TTM 所得税 / TTM 税前利润（截到 [0, 0.5]，缺失取 0.21），分母 ≤ 0 → not_applicable。资产周转 = 营收 / 总资产。
- 动量 `r{n}` = closes[-1] / closes[-1-n] − 1，n = 63/126/189/252 交易日。

测试（NVDA fixture + 构造样例）：
- NVDA：`pe_fwd.status=="ok"` 且 `pe_fwd.inputs[0][0]=="股价"`；`rev_yoy.value > 0.5`；`rev_fwd` 以 FY2026 实际为分母（手算断言）。
- 构造亏损公司（EPS TTM < 0）：`pe_ttm.status=="not_meaningful"`；`eps_yoy.status=="missing"`。
- 构造负权益公司：`pb.status=="not_applicable"`、`roe.status=="not_applicable"`。
- 分析师 2 位：`pe_fwd.status=="missing"`。

- [ ] 五步走，commit `feat(quant): 36 项指标注册表与报表口径计算`

---

### Task 4: EPS 修正（revisions.py）

**Files:** Create `app/services/quant_research/revisions.py`; Test `tests/services/quant_research/test_revisions.py`

输入：`history: list[EstimatePoint]`（`snapshot_date, fiscal_date, eps_avg, revenue_avg, n_analysts`），`as_of`，`fy1_date, fy2_date`。
- `value_at(history, fiscal_date, target_date, tolerance_days=7)`：取 `snapshot_date ≤ target_date` 且差距 ≤ 7 天的最近一条。
- `change(new, old) = (new − old) / |old|`；old 为 0/None → missing。
- 指标：`eps_fy1_30d`、`eps_fy1_90d`、`eps_fy2_90d`、`rev_fy1_90d`（维度 revisions，higher_better，注册进 `METRICS`）。
- `revision_status(history, as_of) -> ("ok"|"accumulating", days_accumulated)`：最早快照距 as_of < 30 天 → accumulating；30~89 天只启用 30d 指标，其余 missing。

测试：构造 100 天序列（EPS 从 5.0 线性升到 5.5）→ `eps_fy1_90d ≈ +(5.5-x)/x`；只有 10 天 → accumulating；负基数（−1.0 → −0.8）→ +0.2（亏损收窄算上修）。

- [ ] 五步走，commit `feat(quant): EPS 修正指标（自有快照）`

---

### Task 5: 阶段判定（stage.py）

**Files:** Create `app/services/quant_research/stage.py`; Test `tests/services/quant_research/test_stage.py`

```python
STAGES = {("-","-","+"): "intro", ("+","-","+"): "growth", ("+","-","-"): "mature",
          ("-","+","+"): "decline", ("-","+","-"): "decline"}
def classify_stage(cfo, cfi, cff) -> str | None:
    if None in (cfo, cfi, cff): return None
    sign = lambda x: "+" if x > 0 else "-"
    return STAGES.get((sign(cfo), sign(cfi), sign(cff)), "shakeout")
```
中文名：intro 初创期 / growth 成长期 / mature 成熟期 / shakeout 调整期 / decline 收缩期；`unprofitable = TTM EPS ≤ 0`。数据来自 TTM `netCashProvidedByOperatingActivities / netCashProvidedByInvestingActivities / netCashProvidedByFinancingActivities`。

测试覆盖五类 + 任一缺失返回 None。commit `feat(quant): Dickinson 现金流阶段判定`

---

### Task 6: 打分聚合（scoring.py）

**Files:** Create `app/services/quant_research/scoring.py`; Test `tests/services/quant_research/test_scoring.py`

- `build_distributions(universe: dict[symbol, (sector_key, dict[key, MetricValue])]) -> dict[(sector_key, key), list[float]]`：只收 status==ok 的值，升序。
- `score_metric(mv, dist, direction, prev_grade) -> ScoredMetric`：ok → percentile_of；not_meaningful → p=0；not_applicable / missing → 不参与（p=None）；dist 长度 < 20 → status 改 `insufficient_sample`，不参与。grade 用防抖。附 `sector_median`、`diff_to_median_pct`、`p10..p90`。
- `score_dimension(scored: list[ScoredMetric], prev_grade)`：参与的 < 半数 → unavailable；否则等权平均。
- `overall(dim_scores, overall_dist, n_analysts, prev_grade)`：可用维度等权 → 综合分；`universe_percentile = percentile_of(综合分, overall_dist)`；等级 = 防抖(universe_percentile)；任一维度分 < 20 → 等级不高于 C+（`capped=True, cap_reason=维度名`）；`n_analysts < 3` → grade None。
- `pick_key_fact(dim)`：维度分 ≥ 50 取参与指标中百分位最高者，否则取最低者。
- `mark_extremes(dims)`：可用维度中分最高 / 最低的标 `is_highest / is_lowest`（并列取固定顺序靠前者）。

测试：一票否决（估值 15、其余 90 → C+ 且 capped）；分析师 2 位 → grade None；不足半数 → unavailable；insufficient_sample；key_fact 选择。commit `feat(quant): 指标打分、维度聚合、综合等级与一票否决`

---

### Task 7: 文案与禁用词（copy.py）

**Files:** Create `app/services/quant_research/copy.py`; Test `tests/services/quant_research/test_copy.py`

- `FORBIDDEN = ["买入","卖出","推荐","看多","看空","强力","上涨空间","抄底","buy","sell","recommend","bullish","bearish","upside","FMP","Financial Modeling Prep","akshare","东方财富","同花顺","Yahoo"]`（英文不区分大小写，按词边界匹配）。
- 模板函数（zh / en）：`key_fact_text`（「营收同比 +94%，高于板块 99% 的公司」/ 估值类「前瞻市盈率 41.2，高于板块 88% 的公司」——估值用「高于」描述数值本身，不用「贵」）、`formula_text(dimension)`（「(12+9+71) ÷ 3 = 30.7」）、`metric_expression(mv)`（按 op 拼：「股价 227.21 ÷ NTM EPS 预期 5.51 = 41.2」）、`position_text`（「高于 88% 的同板块公司 → 百分位 12 → F」）、`overall_text`（「综合分 78.4 · 标普1500 前 8%」）、`cap_text`、`stage_note`、`status_note`（亏损 / 负权益 / 缺失 / 样本不足 / 积累中「修正历史积累中（已 12 天）」）、`DISCLAIMER`。
- 数值格式：倍数 1 位小数，百分比带符号取整，金额按亿 / B。

测试：对所有模板用多组输入生成 zh + en 文本，断言不含 FORBIDDEN。commit `feat(quant): 量化研究文案模板与禁用词守护`

---

### Task 8: 全局 FMP 限流器（app/cache/fmp_budget.py）

**Files:** Create `app/cache/fmp_budget.py`; Test `tests/cache/test_fmp_budget.py`

- Redis 键：`fmp:budget:{分钟时间戳}`（INCR + EXPIRE 120，固定窗口计数）、`fmp:breaker:batch`（SET EX 120）。
- `async def acquire(redis, *, priority: Literal["user","batch"], limit_total=290, limit_batch=150) -> None`：本分钟计数 < 上限则通过；batch 另用 `fmp:budget:batch:{分钟}` 限 150；熔断键存在时 batch 睡到熔断结束；超额时睡到下一分钟开头再试。redis 为 None → 进程内退化实现（单进程计数），保证本地 / 测试可跑。
- `async def report_429(redis, priority)`：batch → 设熔断 120s；记日志 `fmp_rate_limited`。
- 配置（`app/core/config.py` + `.env.example`）：`FMP_RATE_LIMIT_PER_MIN=290`、`FMP_BATCH_RATE_LIMIT_PER_MIN=150`、`FMP_BATCH_BREAKER_SECONDS=120`。

测试（`_FakeRedis` 支持 incr / expire / set nx / get / exists）：batch 第 151 次在同一分钟内阻塞（用可注入的 `now` 与 `sleep` 函数验证，不真睡）；user 不受 batch 上限影响；429 后 batch 等待、user 不等。commit `feat(cache): FMP 全局调用预算（令牌计数 + 批量熔断）`

---

### Task 9: 成分与 FMP 拉取（universe.py / fmp.py）

**Files:** Create `app/services/quant_research/universe.py`, `app/services/quant_research/fmp.py`; Test `tests/services/quant_research/test_universe.py`

- `GICS_KEYS`：维基 `GICS Sector` → 键（`Information Technology`→`information_technology` 等 11 个）+ 中英文名。
- `FMP_SECTOR_TO_GICS`：`Technology→information_technology, Healthcare→health_care, Financial Services→financials, Consumer Cyclical→consumer_discretionary, Consumer Defensive→consumer_staples, Basic Materials→materials, Communication Services→communication_services, Energy→energy, Industrials→industrials, Real Estate→real_estate, Utilities→utilities`。
- `parse_sp_table(html) -> list[(symbol, name, sector_key)]`：`pd.read_html`，找含 `Symbol` 与 `GICS Sector` 列的表，`.`→`-`，丢弃不匹配 `^[A-Z][A-Z\-]{0,6}$` 的代码（验证时遇到过 PRK/TMP 链接串）。
- `async def fetch_sp1500(client) -> list[...]`：三页维基（带 UA），合并去重；Redis 缓存 7 天（`quant:universe:sp1500`）。
- `fmp.py`：`async def fmp_get(client, path, params, *, redis, priority)`：先 `acquire`，429 → `report_429` 后退避重试（最多 4 次），非 200 返回 None；端点封装 `income_quarters(sym, limit=16)`、`cash_quarters(sym, limit=8)`、`balance_latest(sym)`、`estimates_annual(sym)`、`price_light(sym, days=400)`、`profile(sym)`、`earnings_calendar(from,to)`。

测试：`parse_sp_table` 用本地保存的维基 HTML 片段（含一条坏代码行）；映射表覆盖 11 个 FMP sector。commit `feat(quant): 标普1500 成分解析与 FMP 拉取封装`

---

### Task 10: 数据表与迁移（models / repository）

**Files:** Create `app/models/quant_research.py`, `app/services/quant_research/repository.py`; Modify `alembic/env.py`（import 模型）; 迁移 `make migration MSG="add quant research tables"`

模型（均继承 `UUIDModel`）：
- `QuantFundamentalSnapshot`（`quant_fundamental_snapshots`）：`market, symbol, latest_quarter_date, fiscal_period, filing_date, income_quarters: JSON, cash_quarters: JSON, balance: JSON, fetched_at`；唯一 (market, symbol)。
- `QuantEstimateSnapshot`（`quant_estimate_snapshots`）：`market, symbol, snapshot_date, fiscal_date, eps_avg, eps_low, eps_high, revenue_avg, ebitda_avg, ebit_avg, n_analysts`；唯一 (market, symbol, snapshot_date, fiscal_date)；索引 (market, symbol)。
- `QuantSectorDistribution`（`quant_sector_distributions`）：`market, as_of, sector_key（含 "_all" 存综合分）, metric_key, values: JSON`；唯一 (market, as_of, sector_key, metric_key)。
- `QuantResult`（`quant_results`）：`market, symbol, as_of, sector_key, payload: JSON（zh 响应）, payload_en: JSON, grades: JSON（{metric/dim/overall: grade}，防抖用）`；唯一 (market, symbol, as_of)。

repository（异步，`AsyncSessionFactory`）：`upsert_fundamental`、`get_fundamentals(market, symbols)`、`insert_estimates(rows)`（ON CONFLICT DO NOTHING，只补不覆盖）、`get_estimate_history(market, symbol, since)`、`replace_distributions(market, as_of, rows)`、`get_distributions(market, as_of)`、`latest_distribution_date(market)`、`upsert_result`、`get_result(market, symbol)`（最新一天）、`get_prev_grades(market, as_of)`。

验证：`make migrate` 在本地库成功；`uv run pytest tests/services/quant_research/test_repository.py`（用本地 Postgres，标 `@pytest.mark.slow`，无库时 skip）。commit `feat(quant): 量化研究四张表与数据访问`

---

### Task 11: 结果组装（builder.py + schemas）

**Files:** Create `app/schemas/quant_research.py`, `app/services/quant_research/builder.py`; Test `tests/services/quant_research/test_builder.py`, `tests/services/quant_research/test_golden.py`

schema 严格对应设计 §5.1：`QuantResearchOut{market,symbol,name,status,methodology_version,as_of:AsOf,peer_group:PeerGroup,stage:Stage|None,overall:Overall,dimensions:list[Dimension],disclaimer}`；`Dimension{key,name,grade,score,status,status_note,is_highest,is_lowest,key_fact,formula,groups:list[MetricGroup]}`；`MetricOut{key,name,description,direction,value,display_value,status,status_note,percentile,grade,sector_median,diff_to_median_pct,distribution,formula:{expression,inputs},position_text}`。

`build_result(inputs, metrics, scored, dims, overall, stage, lang) -> QuantResearchOut`。维度固定顺序 valuation, growth, profitability, momentum, revisions。

golden：4 只 fixture 用固定板块分布（从 `data/quant_seed` 预计算后存 `tests/fixtures/quant_research/distributions.json`，只含这 4 个板块）跑全流程，与 `tests/fixtures/quant_research/golden_{sym}.json` 比较；首次生成后人工核对 NVDA 数值（前瞻 PE、营收同比、阶段）再提交。另加一条：遍历 4 只 zh/en 输出的全部字符串做禁用词断言。commit `feat(quant): 响应组装与 golden 测试`

---

### Task 12: 夜间批量（batch.py）+ A 股预期快照

**Files:** Create `app/services/quant_research/batch.py`; Test `tests/services/quant_research/test_batch.py`

`async def run_us_batch(as_of: date, *, redis, client, repo)`：
1. 成分 `fetch_sp1500`。
2. 需要重拉报表的股票：库里无快照、或 `earnings_calendar(last_run, as_of)` 中出现且 `epsActual` 非空、或快照 `fetched_at` 超过 100 天 → 拉 income / cash / balance（priority=batch）→ upsert。
3. 每只：`estimates_annual` → 写预期快照（只补不覆盖）；`price_light`；`profile` 仅在无板块信息时拉。
4. 构造 `StockInputs` → `compute_metrics` + revisions → 全体 `build_distributions` → 写分布（含 `_all` 综合分分布，需先算一遍维度分）→ 读前一日 grades → 打分 → `build_result`（zh + en）→ upsert 结果。
5. 结束写 Redis `quant:us:latest_as_of`（TTL 3 天）；单只失败记 `quant_batch_symbol_failed` 并沿用旧数据。

`async def run_cn_estimate_snapshot(as_of)`：沪深300 + 中证500 成分（复用 `signal_radar/constituents._fetch_akshare_index`），逐只 `ak.stock_profit_forecast_ths(symbol, indicator="预测年报每股收益")` 写 `QuantEstimateSnapshot(market="cn", fiscal_date=f"{年度}-12-31", eps_avg=均值, eps_low, eps_high, n_analysts=预测机构数)`；`asyncio.to_thread` + 每只间隔 0.5s；失败跳过。

测试：用假 fetcher（注入函数）跑 3 只股票的迷你 universe，断言分布、结果、预期快照写入调用；断言 batch 优先级传给限流器。commit `feat(quant): 夜间批量计算与 A 股预期快照`

---

### Task 13: 请求服务、路由、调度与首份快照导入

**Files:** Create `app/services/quant_research/service.py`, `app/api/v1/quant_research.py`, `app/services/quant_research/scheduler.py`, `scripts/quant_seed_import.py`; Modify `app/api/v1/api.py`, `app/main.py`, `app/core/config.py`, `.env.example`; Test `tests/api/test_quant_research_api.py`, `tests/services/quant_research/test_scheduler.py`

- `service.get_quant_research(market, symbol, lang, *, redis)`：market != us → `unsupported_market`；Redis `quant:us:{symbol}:{lang}`（TTL 到次日 08:00 北京时间，至少 1h）→ DB 最新结果 → 样本外：拉 6 个接口（priority=user）+ 当日分布打分 + 缓存 1 天；无分布（批量从未跑过）→ `insufficient_data`。
- 路由：`GET /quant-research/methodology`、`GET /quant-research/{market}/{symbol}`（`get_current_user` 鉴权，`limiter.limit` 同 chan 默认额度，symbol 大写校验 `^[A-Z][A-Z\-\.]{0,9}$`）。在 `api.py` 注册 `prefix="/quant-research"`。
- methodology：由 `METRICS` + `BANDS` + 规则常量生成（zh/en），含与 SA 差异说明。
- 调度：`QUANT_BATCH_ENABLED`（默认 true）、`QUANT_BATCH_UTC_HOUR=22`、`QUANT_BATCH_UTC_MINUTE=30`（北京 06:30），工作日次日触发；`_next_trigger(after)` 纯函数单测；lifespan 里 `create_task` + 关闭时 cancel。A 股快照 `QUANT_CN_SNAPSHOT_UTC_HOUR=9`（北京 17:00）。
- `scripts/quant_seed_import.py`：读 `data/quant_seed/2026-09-30/raw/*.est.json` → `insert_estimates(snapshot_date=2026-09-30)`，幂等。

API 测试：`dependency_overrides` 跳过鉴权，monkeypatch `service.get_quant_research` 返回 fixture；断言 200、字段、`unsupported_market`、非法 symbol 422。commit `feat(quant): /quant-research 接口、夜间调度与首份预期快照导入`

---

### Task 14: 收尾验证

- [ ] `uv run pytest tests/services/quant_research tests/cache tests/api/test_quant_research_api.py -v` 全绿
- [ ] `make check`（ruff + pyright）无新增错误
- [ ] 本地真实跑一次：`uv run python -c "import asyncio; from app.services.quant_research.batch import run_us_batch_cli; asyncio.run(run_us_batch_cli(limit=60))"`（只跑 60 只、priority=batch、150/分钟），再 `curl` 本地接口看 NVDA 响应，人工核对 3 个数与验证数据一致
- [ ] 导入首份快照：`uv run python scripts/quant_seed_import.py`
- [ ] 更新 `CLAUDE.md` 功能模块地图（量化研究行 + FMP 预算约束说明）
- [ ] commit `docs(quant): CLAUDE.md 模块地图与 FMP 预算约束`
