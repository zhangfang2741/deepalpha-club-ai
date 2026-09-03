# A 股投研内容平台 —— 设计文档（第一版）

> 定位：类 SeekingAlpha 的 **A 股投研内容社区**。平台供数据，经纪人（分析师）产出投资报告，平台在报告发布当时打上 K 线标记并持续回测其后续走势，统计经纪人的**预测准确率**；用户订阅经纪人或订阅平台以获取报告。
>
> 本文档定义第一版（MVP）的产品概念、角色、数据模型、API 地图、准确率与回测机制、盈利模型、以及里程碑。**复用现有 deepalpha-club-ai 后端技术栈**（FastAPI + SQLModel + asyncpg + Alembic + Redis + Next.js），作为新的一批模块落地。

## 1. 三个角色

| 角色 | 英文 | 能做什么 |
|------|------|----------|
| **平台** | platform | 提供数据（行情/基本面/关键指标/证监会公告/分析师预测）；对每篇报告在发布当时打 K 线标记；持续回测并统计经纪人准确率；管理订阅与结算 |
| **经纪人** | analyst / broker | 撰写并发布针对某只 A 股标的的投资报告（看多/看空/中性 + 时限）；查看自己的准确率与订阅者 |
| **用户** | user / subscriber | 浏览平台数据；订阅单个经纪人（看其实时报告）或订阅平台（看全部报告）；查看每篇报告的标记点与后续 K 线，以及经纪人历史准确率 |

一个登录账号默认是「用户」；当它拥有一条 **Analyst 档案**（经纪人认证）后即同时是「经纪人」。平台角色由后台管理员标志位控制（`User.is_staff`，后续加）。

## 2. 核心闭环

```
经纪人写报告(标的+方向+时限)
        │  发布
        ▼
平台记录「标记点」= 发布时刻的收盘价 mark_price + mark_date
        │
        ▼
到达时限(horizon_days) → 平台取到期日收盘价 → 计算实际收益 & 方向是否命中
        │
        ▼
汇总成经纪人「准确率」(命中数 / 已到期报告数) → 榜单
        │
        ▼
用户看报告详情：标记点 + 后续真实 K 线 + 命中与否 + 该经纪人历史准确率
        │  被说服 → 订阅
        ▼
盈利：订阅经纪人（看其实时报告）/ 订阅平台（看全部报告）
```

## 3. 准确率定义（第一版：**方向 + 时限**）

已与产品确认采用最简单、最客观、最好统计的口径：

- 报告发布时经纪人声明：**方向** `direction ∈ {BULLISH 看多, BEARISH 看空, NEUTRAL 中性}` + **时限** `horizon_days`（如 20 交易日 / 60 自然日）。
- 平台在发布当时记录 `mark_price`（发布时最新收盘价）与 `mark_date`。
- 到期时（`mark_date + horizon_days`，取该日或其后第一个交易日的收盘价 `price_at_horizon`）计算：
  - `actual_return_pct = (price_at_horizon - mark_price) / mark_price * 100`
  - 命中判定 `is_correct`：
    - 看多：`actual_return_pct >= hit_threshold_pct`
    - 看空：`actual_return_pct <= -hit_threshold_pct`
    - 中性：`abs(actual_return_pct) <= neutral_band_pct`
  - `hit_threshold_pct` 默认 `0`（严格方向），可在平台配置为 `+X%` 提高门槛（避免「涨 0.1% 也算看多命中」）。第一版默认 `hit_threshold_pct = 0`、`neutral_band_pct = 3`。
- **准确率** `accuracy = correct_count / resolved_count`，只统计**已到期**（resolved）的报告；未到期报告 `status = PENDING` 不计入分母。
- 同时展示 `avg_return`（已到期报告的平均实际收益，衡量「不只对方向、还赚多少」）。

> 第二版可扩展：目标价命中、最大回撤、按持有期年化、置信区间/样本量加权（样本少的经纪人不给高排名）。这些留作后续，数据模型已为 `target_price` 预留字段。

## 4. 数据模型（SQLModel，均继承 `app.db.base.UUIDModel`）

### 4.1 `Analyst` — 经纪人档案（`analysts`）
| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | int, unique, index | 关联现有 `User.id` |
| display_name | str(64) | 展示名 |
| bio | text | 简介 |
| avatar_url | str, null | 头像 |
| verified | bool | 平台是否已认证 |
| monthly_price_cents | int | 订阅该经纪人的月费（分），0=免费 |
| status | str(16) | active / suspended |

### 4.2 `Report` — 投资报告（`reports`）
| 字段 | 类型 | 说明 |
|------|------|------|
| analyst_id | UUID, index | FK Analyst |
| symbol | str(16), index | 归一化 A 股代码，如 `600519.SH` / `000001.SZ` |
| symbol_name | str(64) | 标的名称快照 |
| title | str(200) | 标题 |
| summary | str(500) | 摘要（列表页展示） |
| content | text | 正文（Markdown） |
| direction | str(8), index | BULLISH / BEARISH / NEUTRAL |
| horizon_days | int | 时限（自然日） |
| target_price | float, null | 目标价（可选，为第二版口径预留） |
| status | str(12), index | DRAFT / PUBLISHED |
| visibility | str(12) | SUBSCRIBER（默认，仅订阅可见实时）/ PUBLIC（平台设为公开样例） |
| mark_price | float, null | 发布当时收盘价（打标记） |
| mark_date | str(10), index | 发布当时交易日 YYYY-MM-DD |
| published_at | datetime tz, null, index | 发布时间 |

### 4.3 `ReportOutcome` — 回测结果（`report_outcomes`，report_id 唯一）
| 字段 | 类型 | 说明 |
|------|------|------|
| report_id | UUID, unique, index | FK Report |
| status | str(12), index | PENDING / RESOLVED |
| horizon_end_date | str(10) | 计划到期日 |
| price_at_horizon | float, null | 到期日收盘价 |
| actual_return_pct | float, null | 实际收益率 % |
| is_correct | bool, null | 是否命中 |
| resolved_at | datetime tz, null | 回测完成时间 |

> 拆表而非塞进 Report：回测是可重算的派生数据；口径（阈值）调整时可整表重算，不动原始报告。

### 4.4 `PriceBar` — 日 K 线缓存（`price_bars`，symbol+date 唯一）
| 字段 | 类型 | 说明 |
|------|------|------|
| symbol | str(16), index | 归一化代码 |
| date | str(10), index | 交易日 |
| open/high/low/close | float | 前复权价 |
| volume | float | 成交量 |

数据源：东方财富行情接口（与 akshare A 股/港股接口同源，直连更稳；见 `app/services/skills/kline.py`）。akshare 用于实时快照与基本面。落库做缓存，减少对外请求、支撑回测与详情页 K 线渲染。

### 4.5 `Subscription` — 订阅（`subscriptions`）
| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | int, index | 订阅者 |
| tier | str(12), index | ANALYST（订阅单个经纪人）/ PLATFORM（订阅平台看全部） |
| analyst_id | UUID, null, index | tier=ANALYST 时指向经纪人 |
| status | str(12), index | ACTIVE / EXPIRED / CANCELED |
| price_cents | int | 本次订阅价格（分） |
| start_at / end_at | datetime tz | 有效期 |

## 5. 订阅门控（可见性规则）

判定「用户 U 能否看报告 R 的正文」：
1. R 是自己写的（U 是 R 的经纪人本人）→ 可见。
2. R.visibility = PUBLIC → 可见。
3. U 有 **ACTIVE 的 PLATFORM** 订阅 → 可见全部报告。
4. U 有 **ACTIVE 的 ANALYST** 订阅且 `analyst_id = R.analyst_id` → 可见该经纪人报告。
5. 否则：只返回 `summary` + 标记点 + 准确率等元数据，正文 `content` 置空并标 `locked=true`（前端引导订阅）。

榜单、经纪人主页、报告列表（摘要）、K 线标记与回测结果**始终公开**——这是平台的「信任展示」，用来把游客转化为订阅者。**正文**才是付费墙后的内容。

## 6. API 地图（挂载于 `/api/v1`）

| 前缀 | 端点（MVP） | 说明 |
|------|-------------|------|
| `/astock` | `GET /kline?symbol=&start=&end=` | 日 K 线（带缓存） |
| | `GET /quote?symbol=` | 实时快照 |
| | `GET /fundamental?symbol=` | 基本面/关键指标 |
| | `GET /search?q=` | 标的搜索（代码/名称） |
| `/analysts` | `POST /` | 成为经纪人（建档） |
| | `GET /` | 经纪人列表 |
| | `GET /leaderboard` | 准确率榜单 |
| | `GET /{analyst_id}` | 经纪人主页（含准确率、报告数） |
| | `GET /{analyst_id}/reports` | 该经纪人报告列表 |
| `/reports` | `POST /` | 写报告（草稿） |
| | `POST /{id}/publish` | 发布（此刻打 K 线标记 mark_price） |
| | `GET /` | 报告流（订阅门控） |
| | `GET /{id}` | 报告详情（标记点 + 后续 K 线 + 回测 + 门控正文） |
| | `POST /{id}/evaluate` | （平台/定时）触发回测到期结算 |
| `/subscriptions` | `POST /` | 订阅（经纪人 / 平台） |
| | `GET /me` | 我的订阅 |
| | `DELETE /{id}` | 取消订阅 |

回测结算除手动 `POST /reports/{id}/evaluate` 外，后续接入定时任务（复用 supply_chain 的 scheduler 模式）每日扫描到期未结算报告批量结算。

## 7. 盈利模型

- **订阅经纪人**（ANALYST tier）：看某经纪人的**实时**报告。经纪人自定月费，平台抽成。
- **订阅平台**（PLATFORM tier）：看全平台所有报告。平台统一定价。
- 免费层：所有人可见榜单、经纪人准确率、报告摘要与 K 线标记/回测（信任展示），正文加锁。
- 结算/分成、优惠券等留作后续；第一版只落地订阅关系与门控，支付用占位（记录 `price_cents`，不接真实支付网关）。

## 8. 前端规划（Next.js 16，复用现有 shadcn + lightweight-charts）

| 页面 | 路径 | 内容 |
|------|------|------|
| 榜单 | `/leaderboard` | 经纪人准确率排行 |
| 经纪人主页 | `/analysts/[id]` | 简介 + 准确率 + 报告流 + 订阅按钮 |
| 报告详情 | `/reports/[id]` | K 线（标记点高亮 + 后续走势）+ 正文（门控）+ 回测结论 |
| 报告流 | `/feed` | 已订阅内容流 |
| 写报告 | `/studio` | 经纪人编辑器（选标的/方向/时限/正文） |
| 标的页 | `/symbols/[symbol]` | 平台数据（行情/基本面）+ 该标的下的报告 |

K 线标记：用 lightweight-charts 的 `markers` 在 `mark_date` 处打标记，并叠加时限区间与到期命中/未命中着色。

## 9. 里程碑

- **M1（本次）**：设计文档 + 后端数据模型/迁移 + astock 数据客户端 + 报告打标/回测/准确率服务 + API + 订阅门控 + 单测。
- **M2**：前端页面（榜单/经纪人主页/报告详情/写报告）。
- **M3**：定时回测调度、经纪人认证后台、支付占位→真实支付、准确率口径 v2（目标价/加权）。

## 10. 技术落点（复用现有栈）

- 模型：`app/models/{analyst,report,price_bar,subscription}.py`，注册进 `alembic/env.py`。
- Schema：`app/schemas/{astock,analyst,report,subscription}.py`。
- 服务：`app/services/astock/`（数据源）、`app/services/reports/`（准确率纯函数 + 回测编排）。
- API：`app/api/v1/{astock,analysts,reports,subscriptions}.py`，注册进 `app/api/v1/api.py`。
- 认证：复用 `app/api/v1/auth/dependencies.py` 的 `get_verified_user_id`。
- 数据源直连东方财富（不走代理，见 kline.py 注释）；akshare 用于快照/基本面。
