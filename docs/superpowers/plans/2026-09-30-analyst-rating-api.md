# 分析师评级接口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现设计文档 §5.2：`GET /api/v1/analyst-upgrades/overview/{symbol}`，为缠论 App 详情页第 3 个 Tab「分析师评级」提供评级分布与趋势、目标价、业绩预期 vs 实际、最近评级变动。

**Architecture:** 纯函数整理层（`app/services/analyst_upgrade/overview.py`：把 FMP 原始响应整理成响应 schema，含中文动作 / 评级标签与中性文案）+ 拉取编排（复用 `quant_research.fmp.FmpClient`，priority="user"，经全局 FMP 预算）+ 路由（现有 `app/api/v1/analyst_upgrade.py` 加一个接口，Redis 缓存 6h）。

**Tech Stack:** FastAPI / httpx / redis-py / pydantic / pytest

---

### Task 1: 整理层与 schema

**Files:** Create `app/services/analyst_upgrade/overview.py`; Modify `app/schemas/analyst_upgrade.py`（新增 `AnalystOverviewOut` 等）; Test `tests/services/analyst_upgrade/test_overview.py` + fixtures `tests/fixtures/analyst_upgrade/NVDA.*.json`（grades-historical / price-target-consensus / price-target-summary / earnings / grades / quote-short，6 次调用）

- 评级分布：**只用** `grades-historical`（不混用 `grades-consensus`，两者口径不同），最新一月为当前分布，最多 12 个月趋势；`change_text`：「近 3 个月：给出「买入」及以上的分析师由 58 位增至 60 位」（比较最新月与 3 个月前那一月的强买 + 买入人数）。
- 目标价：最高 / 最低 / 中位 / 均值 + 现价；`vs_price_pct` = 中位 / 现价 − 1（算术差，文案写「较现价 +41.9%」，不写「上涨空间」）；近月 / 季 / 年发布次数。
- 业绩：`earnings` 中 `epsActual` 非空的最近 4 季（实际、预期、差异 %），以及日期在今天之后最近的一条（下次披露日、EPS / 营收预期）。
- 最近评级变动：`grades` 最近 10 条；动作中文（upgrade 上调 / downgrade 下调 / maintain 维持 / init 首次覆盖 / reiterated 重申），评级标签保留原文并给中文（Buy 买入、Outperform 跑赢大盘、Overweight 增持、Hold 持有、Neutral 中性、Underperform 跑输大盘、Underweight 减持、Sell 卖出……未知的保留原文）。
- 我们自己生成的文案（change_text、说明、免责）过禁用词扫描；评级标签字段豁免（引述分析师原话）。
- 非美股 → `status="unsupported_market"`。

### Task 2: 拉取编排 + 路由 + 缓存

**Files:** Modify `app/api/v1/analyst_upgrade.py`; Create `app/services/analyst_upgrade/overview_service.py`; Test `tests/api/test_analyst_overview_api.py`

- `GET /analyst-upgrades/overview/{symbol}?lang=zh`，鉴权同 chan（`get_current_user`），`limiter.limit("20 per minute")`，Redis 缓存键 `analyst_upgrade:overview:v1:{symbol}:{lang}`，TTL 6h。
- 6 个端点并发拉取（FmpClient priority=user）；任一失败只让对应区块为空，不整体失败；全部失败 → `status="insufficient_data"`。

### Task 3: 收尾

- ruff / pyright 新增 0 错误；全量测试与 master 对比无新增失败；CLAUDE.md 模块地图补充。
