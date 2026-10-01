# 市场雷达页：宏观与行业维度设计

日期：2026-10-01
范围：iOS 缠论 App「市场雷达」Tab + 后端 regime / macro / signal_radar

## 背景与目标

市场雷达页现在只有两层：情绪（顶部三地恐慌指数卡片，兼做市场切换）与个股（缠论买卖点气泡）。
补上**宏观**与**行业**两个维度，形成自上而下的一条链：

> 宏观（环境友不友好）→ 情绪（冷还是热）→ 行业（钱往哪走）→ 个股（谁有信号）

三个市场（美股 / A 股 / 港股）都要覆盖，分三期交付（见「实施顺序」）。

## 已确认的决定

1. **布局**：雷达页顶部升级为「宏观 / 情绪 / 行业」三格温度计，每格一句结论，点开是完整弹层；雷达仍占主屏，页面不滚动。
2. **市场切换**：三格上方加「美股 | A股 | 港股」分段控件，替代「点卡片切市场」（去掉「点击卡片切换市场」提示）。
3. **行业联动**：在行业弹层点某个行业 → 雷达切到该市场的宽基 universe，并且只显示该行业的气泡；顶部出现可清除的筛选标签。
4. **三地都做**。

## 1. 页面结构（iOS）

```
[ 美股 | A股 | 港股 ]
┌宏观────┐┌情绪────┐┌行业────┐
│逐利 72%│ │恐慌 38 │ │半导体 ↑│
│周三 CPI│ │ ~~~~~ │ │能源 ↓  │
└────────┘└────────┘└────────┘
[半导体 ✕]              ← 仅行业筛选时出现
      ( 气泡雷达 )
[日期轨]
```

- 三格等宽、等高，固定高度（与现在恐慌卡片的内容区一致），异步加载时不挤动下面的雷达。
- **宏观格**：状态标签（逐利 / 观望 / 避险）+ 该状态的后验概率；第二行是未来 7 天最近的一个高重要度事件（没有事件时显示状态持续天数）。
- **情绪格**：沿用现有恐慌指数（分数 + 近 60 日迷你走势），数据接口不变。
- **行业格**：相对大盘强弱（`rs_vs_market`）最强的一个行业 ↑ 和最弱的一个行业 ↓。
- 三格各自加载、各自失败：失败的那格显示「重试」，不影响其他两格和雷达。
- A 股 / 港股数据未上线时，宏观格和行业格显示「数据建设中」，不可点。
- 现有 `PanicIndexStrip` 拆分为：`MarketSegmentPicker`（分段控件）+ `MarketThermometer`（三格容器）+ 三个格子视图；`PanicIndexDetailSheet` 原样保留，挂到情绪格上。

## 2. 弹层内容

### 宏观弹层

1. **状态**：当前状态 + 三态概率条（逐利 / 观望 / 避险）+ 近一年状态色带（按 `confirmed_label` 着色）。
2. **驱动因素**（每市场 5 个）：当前值、近 20 个交易日的方向箭头、一句大白话（例如「美元走强，对风险资产偏不利」）。

   | 市场 | 驱动因素 |
   |---|---|
   | 美股 | 10 年期美债、10Y-2Y 利差、美元指数、VIX、原油 |
   | A 股 | 中债 10 年期、美元兑离岸人民币、两市成交额、融资余额、股债利差（沪深 300 股息率 − 10 年期国债） |
   | 港股 | 美债 10 年期、HIBOR（1 个月）、美元兑离岸人民币、南向资金（20 日累计净买入）、恒指波动率 |

   北向资金自 2024-08 起不再按日披露，**不使用**。
3. **宏观日历**：未来 7 天的高重要度事件，时间按该市场本地时区显示；港股合并显示美国和中国的事件。
4. 底部一句免责说明。

### 行业弹层

- 行业列表按 `rs_vs_market` 从强到弱排序，每行：行业名、状态色点、相对强弱数值、「N 买 M 卖」（该市场宽基 universe 在当前选中日的雷达统计）。
- 点某一行 → 关闭弹层，雷达切到宽基 universe，并设置行业筛选；顶部显示「行业名 ✕」，点 ✕ 清除筛选并恢复进入前的 universe。
- 美股有子行业的行业保留下钻（现有 `/regime/sectors/{sector}/children`）。
- 行业分类：美股用现有 12 个板块（`regime.constants.SECTORS`）；A 股用申万一级 31 个；港股用恒生行业分类（约 12 个）。

## 3. 后端设计

### 3.1 regime 按市场配置

- 新增 `app/services/regime/markets.py`：每个市场一份 `MarketRegimeConfig`（`offense` / `defense` / `cash` 三组篮子、`benchmark`、波动率代理、`sectors` 列表、数据源）。现有 `constants.py` 里的美股常量迁到 `us` 配置，行为不变。
  - **us**：保持现状（XLK/XLY/XLI/SMH vs XLU/XLP/XLV vs BIL/SHV，基准 SPY）。
  - **cn**：进攻篮子用电子、计算机、电力设备等申万行业指数，防御篮子用银行、公用事业、食品饮料，现金篮子用短融 / 货基 ETF，基准沪深 300。
  - **hk**：进攻篮子用恒生科技相关，防御篮子用公用、电讯、高息银行，现金篮子用港元货币 ETF，基准恒指。
  - 港股行业指数若没有稳定的数据源：用宽基成分股按行业标签合成等权指数（复用 `baskets.basket_index`）。
- `pipeline` / `sector_pipeline` / `fetcher` 接收 `market` 参数；HMM（`hmm.py`、`engine.py`）不改。
- **数据表**：`regime_features`、`regime_sector_features` 加 `market` 列（默认 `us`）。唯一约束分别改为 `(market, trade_date)` 和 `(market, trade_date, sector)`。用 `alembic revision --autogenerate` 生成迁移，已有数据回填为 `us`。
- 下游已经用 `regime_features` 的地方（例如 `factor_weight`）显式按 `market="us"` 过滤，保证行为不变。

### 3.2 新模块 `app/services/macro/`

- `drivers.py`：每个市场的驱动因素定义（序列 id、数据源、单位、方向含义）+ 纯函数 `evaluate_driver(series) -> DriverOut`（当前值、20 日变化、方向、大白话）。
- `calendar.py`：美股用 FMP 经济日历（经 `app/cache/fmp_budget.acquire` 限速），A 股用 akshare；统一成 `{time, country, event, importance}`，只保留高重要度。
- `fetcher.py`：yfinance / akshare / FMP 取数；失败的单个因素返回 `unavailable`，不影响其他因素。
- 缓存：`app/cache/macro_cache.py`，key `macro:{market}:{date}`，TTL 1 小时；日历 key `macro:calendar:{market}`，TTL 6 小时。

### 3.3 接口

| 接口 | 用途 |
|---|---|
| `GET /api/v1/market-overview/{market}` | 宏观格 + 行业格摘要，一次返回（情绪格仍走 `/panic-index`）；Redis 缓存 10 分钟 |
| `GET /api/v1/macro/{market}` | 宏观弹层（状态历史 + 驱动因素 + 日历） |
| `GET /api/v1/regime/sectors?market=` | 已有接口，新增 `market` 参数（默认 `us`），向后兼容 |

`market-overview` 中某个市场的数据未就绪时返回 `available=false`，App 显示「数据建设中」。

### 3.4 雷达行业标签与统计

- 新增 `app/services/signal_radar/sector_tags.py`：宽基成分股 → 行业 key。
  - 美股：复用基本面研究已有的 GICS 板块，映射到 12 个 regime 板块 key。
  - A 股：akshare 申万一级行业成分。
  - 港股：恒生行业分类（取不到时用 FMP profile 的 sector 兜底映射）。
  - 结果按周缓存（`signal_radar:sector_tags:{market}`，TTL 8 天）。
- 雷达气泡输出加 `sector`（可空），每日快照加 `sector_counts: {sector_key: {buy, sell}}`。
- 雷达接口加可选参数 `sector`：只返回该行业的气泡（在服务端过滤快照，不重新扫描，不绕开扫描锁）。
- 升雷达缓存键版本。

## 4. 实施顺序

1. **第一期：美股打通全链路**——iOS 分段控件 + 三格 + 两个弹层 + 行业筛选；后端 regime 按市场配置（只有 us）、macro 模块（us）、market-overview、雷达行业标签（us）。A 股 / 港股的宏观格和行业格显示「数据建设中」。
2. **第二期：A 股**——cn 配置、申万行业、宏观驱动、日历、成分股行业标签；HMM 先回测验证状态稳定性再上线。只动后端，App 不用发版。
3. **第三期：港股**——开头先实测港股行业指数、HIBOR、恒指波动率在 akshare 里的可用性，再按结果确定数据源；其余同第二期。

## 5. 文案

- 只描述环境（例如「资金偏向进攻板块」「美元走强」），不出现买卖导向的词，不出现数据供应商名。
- 宏观弹层、行业弹层底部各加一句免责说明。
- 中英文文案走现有 `L()` 本地化。

## 6. 测试

- `tests/services/regime/`：每个市场配置的完整性（篮子非空、行业 key 唯一、基准存在）；迁移后 `market="us"` 的结果与迁移前一致。
- `tests/services/macro/`：`evaluate_driver` 的方向判定与大白话（含数据不足 / 单因素缺失）；日历重要度过滤与时区。
- `tests/services/signal_radar/`：`sector_counts` 与气泡逐一对得上；`sector` 过滤只出该行业气泡；没有标签的成分股不进任何行业统计。
- `tests/api/`：`market-overview` 在数据未就绪时返回 `available=false`。

## 风险

- 港股行业指数、HIBOR、恒指波动率的数据源稳定性未验证（第三期开头先实测）。
- A 股 / 港股的 HMM 历史样本较短，刚上线时状态概率可能不稳；上线前做回测，必要时延长「连续 N 日确认」窗口。
- 顶部多出分段控件约 32pt，挤占雷达画布；需要在小屏机型（iPhone SE）上验证气泡布局。
