# 机构资金信号（Institutional Signals）实施计划

> 状态：规划中 · 分支 `claude/institutional-funding-signals-bvwzmv` · 2026-07-03

## 一、产品定位

把「机构资金信号手册」落地成一个**每天回答五个问题**的产品能力，而不是又一个堆指标的仪表盘。

Agent / 前端页面对每支标的只输出**状态（State）**和**五维评分**，原始数据折叠在下钻里：

| 维度 | 核心问题 | 数据 |
|------|----------|------|
| **Expectation 预期** | 分析师是不是开始重新定价未来？ | EPS Revision、Revenue Revision、Target Price、Rating |
| **Positioning 仓位** | 资金是不是已经开始下注？ | Call/Put Volume、OI、IV Rank |
| **Participation 参与度** | 其他资金开始跟了吗？ | Relative Volume、成交额、Gap |
| **Fundamental 基本面** | 企业经营有没有真正改善？ | Guidance、Transcript、Earnings Surprise |
| **Confirmation 确认** | 长期资金确认了吗？ | Insider、13F、ETF Flow |

五维各自归一到 0–100，组合成**状态标签**（见第四节），最终输出一句话结论。

## 二、数据可得性核对（决定分期的关键）

| 维度 | 信号 | 数据源 | 可得性 |
|------|------|--------|--------|
| Expectation | EPS/Revenue 预测 | FMP `analyst-estimates` | ✅ 现有 `fmp_data.fetch_analyst_estimates` |
| Expectation | 目标价修正 | FMP `price-target`、grades-historical | ✅ `analyst_upgrade` 已在用 |
| Expectation | 评级升降 | FMP `grades` / upgrades-downgrades | ✅ `analyst_upgrade` 已在用 |
| Participation | Relative Volume / Gap | FMP `historical-price-eod` | ✅ 现有价格抓取 |
| Fundamental | Earnings Surprise 历史 | FMP `earnings-calendar` | ✅ `fmp_data.fetch_earnings` |
| Fundamental | Guidance / Transcript | FMP `earningsTranscript`（MCP） | 🟡 拿得到全文，Guidance 需 NLP 抽取 |
| Confirmation | Insider Buy/Sell | FMP `insiderTrades`（MCP） | ✅ |
| Confirmation | 13F | FMP `form13F`（MCP） | ✅ 季度滞后 |
| Confirmation | ETF Flow | 复用 `app/services/etf` | ✅ 已有 |
| **Positioning** | **Call/Put Vol、OI、IV** | **FMP 不提供** → `yfinance.option_chain()` | 🔴 需换源，免费但不稳定 |
| B 级 | Short Interest | FMP 覆盖不全 | 🟡 尽力而为 |

**结论**：Expectation + Participation + Fundamental + Confirmation 四维用 FMP + 现有代码即可覆盖；唯一的真实风险是 **Positioning（期权）**，需要 yfinance 或付费源（Polygon / Tradier）。因此把 Positioning 单独排到 Phase 2，先用四维交付价值。

## 三、后端架构（对齐 etf / industry_panic 模式）

```
app/services/institutional_signals/
├── __init__.py
├── constants.py      # universe、五维权重、阈值（放量倍数、修正天数窗口等）
├── fetchers.py       # 各源抓取：estimates / grades / price / earnings / insider / options
├── dimensions.py     # 五个 compute_<dimension>() → 0-100 子分 + 明细
├── states.py         # 组合规则：五维模式 → State 标签
└── calculator.py     # 编排：symbol → SignalReport

app/api/v1/institutional_signals.py   # GET /api/v1/institutional-signals?symbol=AAPL
app/schemas/institutional_signals.py  # SignalReport / DimensionScore / SignalState
```

- 在 `app/api/v1/api.py` 注册，prefix `/institutional-signals`。
- Redis 缓存 `institutional_signals:{symbol}:v1`，TTL 1 小时（盘中）；Redis 故障降级实时算，沿用 industry_panic 的 `get_redis_optional` 模式。
- 抓取并发用 `asyncio.gather` + httpx（对齐 analyst_upgrade），各源独立 try/except，单源失败不拖垮整份报告（该维度标记 `partial`）。
- 日志用 structlog，事件名 `institutional_signals_*`。

### 修正（Revision）怎么算

- **目标价 / 评级**：FMP grades-historical、price-target 本身带时间戳 → 直接统计 30/60/90 天窗口内的**升级次数与幅度**，无需自建快照。
- **EPS / Revenue 估值修正**：FMP `analyst-estimates` 是即时前瞻值，测「修正」需要历史快照。**Phase 4** 引入 `SignalSnapshot(UUIDModel)` 每日落库 + 定时任务重建趋势；Phase 1 先用「分析师上调家数 / 目标价环比」作为 Expectation 的代理指标。

## 四、状态引擎（产品只显示状态，不显示数据）

`states.py` 把五维子分与关键布尔量映射成标签（对应手册的组合）：

| 状态 | 触发条件（简化） | 含义 |
|------|------------------|------|
| 🔥 Institution Accumulation | EPS↑ + Call OI↑ + Call Vol↑ + IV↑ | 机构建仓 |
| 📈 Expectation Upgrade | EPS↑ + TP↑ + Rating 连升 | 市场预期提升 |
| 🚀 Breakout Confirmation | Relative Vol↑ + 价格突破 + EPS↑ | 趋势确认 |
| ⚡ Event Trading | IV↑ + Call Vol↑ + OI→ | 短线事件投机（非真机构） |
| 💰 Smart Money（真资金） | Call Vol↑ + OI↑ + IV↑ + Price→ | 资金已到、价格未动，最值得研究 |
| 🌱 Fundamental Turn | Revenue Rev↑ + Guidance↑ + Transcript 强调需求 | 基本面真实改善 |
| ❄ Distribution | Put OI↑ + EPS↓ + Insider Sell + 放量 | 资金撤退 |
| ⚪ Neutral | 无显著组合 | 观望 |

每个状态附**证据链**（命中的具体信号），保证可解释、可回溯。

## 五、分期交付

- **Phase 0（半天，spike）**：验证三个数据源真能拿到——yfinance 期权链、FMP grades-historical 时间戳、earnings surprise 历史。产出可弃的验证脚本。
- **Phase 1（MVP）**：Expectation + Participation 两维（数据最全）+ 状态引擎骨架 + API + 前端卡片。先能对单标的出「预期提升 / 趋势确认 / 中性」三类状态。
- **Phase 2**：Positioning——接 yfinance 期权链，算 Call/Put Vol 相对量、OI 变化、IV Rank，解锁 Smart Money / Event Trading / Accumulation 状态。
- **Phase 3**：Fundamental（earnings surprise + transcript 需求关键词）+ Confirmation（insider + 13F + 复用 ETF flow），补齐 Fundamental Turn / Distribution。
- **Phase 4**：`SignalSnapshot` 持久化 + 定时任务（真实 EPS/Revenue 修正趋势）+ 每日「五问」Brief 接入 LangGraph Agent / chatbot skill。

## 六、TDD 与验证

- 每维 `compute_<dimension>()` 用固定 fixture 写 failing test（对齐 `industry_panic/fixture.py`），断言子分与状态标签。
- 状态引擎单测覆盖手册六大组合的边界。
- PR 前：`uv run ruff check app/` + `cd frontend && npx tsc --noEmit`。

## 七、已定方向（默认值，可调整）

1. **Positioning 数据源** → **yfinance**（已是项目依赖、零新增成本）。MVP 够用，验证信号质量后再评估切换 Polygon/Tradier。
2. **产品形态** → **单标的按需查询**先行。先验证五维评分与状态判断的准确性；每日全 universe 扫榜留到 Phase 4。
3. **universe 范围** → **复用 `analyst_upgrade` 现成的 SP500/NASDAQ100 名单**，零额外维护；用户自选股按需再加。
