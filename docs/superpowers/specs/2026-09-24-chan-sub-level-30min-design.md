# 缠论次级别确认（日线定方向 × 30 分钟找买卖点）设计

日期：2026-09-24

## 目标

在日线缠论分析之外，给出「次级别确认」：用日线判定大方向，用 30 分钟级别的缠论买卖点寻找更精确的进场/离场时机，并判断两者是否共振。覆盖美股、港股、A 股。展示在 iOS 分析详情页（卡片）与 iOS 信号雷达（气泡标记）。网页端不做。

## 已确认的决策

- 市场：美股、港股、A 股都做。
- 形态：联动提示（非单纯的 30 分钟周期切换）。
- 展示位置：iOS 分析详情页卡片 + 信号雷达入榜候选（约 15 只）补算；网页不做。
- 数据请求成本：可接受，需加缓存。

## 数据源（2026-09-24 实测）

- 美股：FMP `stable/historical-chart/30min`，单次请求约一个月（约 260 根），用 `from/to` 分段拉取可拼出更早历史。
- 港股 / A 股：FMP 当前套餐返回 402，不可用。走现有 `_fetch_cn_hk` 链路：Yahoo chart `interval=30m`（Yahoo 分钟线最多近 60 天），网络不可达时回退东方财富 `klt=30`。
- 取数窗口：统一取最近 40 个自然日（美股分两段请求）。

## 联动判定规则

- **日线方向**：日线分析的 `recommendation.bias`（bullish / bearish / neutral），即详情页「技术面偏强/偏弱/僵持」的多因子加权结论，不另起标准。
- **30 分钟信号**：对 30 分钟 K 线跑同一套缠论分析（czsc 结构 + 买卖点），取「最近 2 个交易日」（30 分钟 K 线中最后两个不同日期）内的买卖点。
- **结论 verdict**：
  - `resonance_buy`：日线偏多，且 30 分钟近期有买点 → 共振买点
  - `resonance_sell`：日线偏空，且 30 分钟近期有卖点 → 共振卖点
  - `counter_trend`：30 分钟近期信号与日线方向相反 → 逆势信号（次级别反弹/回调）
  - `waiting`：日线中性，或 30 分钟近期无信号 → 等待次级别信号
  - `unavailable`：30 分钟数据取不到或不足以分析 → 暂不可用（不影响日线分析）
- 若 30 分钟近期同时有买点和卖点，以最新的一个为准。

## 组件

| 位置 | 变化 |
| --- | --- |
| `app/services/skills/kline.py` | `fetch_kline` 支持 `freq="30min"`：美股 FMP 30min 分段拉取；港股/A 股 Yahoo `interval=30m`（UTC→交易所本地时区），东方财富 `klt=30` 回退。时间为交易所本地 `YYYY-MM-DD HH:MM`。30 分钟缓存 TTL 约 15 分钟。 |
| `app/services/chan/czsc_adapter.py` | 时间格式化改为按时刻：零点输出 `YYYY-MM-DD`（日线/周线不变），否则输出 `YYYY-MM-DD HH:MM`，避免同日多根 30 分钟 K 线时间冲突。 |
| `app/services/chan/analyzer.py` / `czsc_signals.py` | `freq` 支持 `"30min"` → `Freq.F30`，czsc 信号配置标签 `30分钟`。 |
| `app/services/chan/sub_level.py`（新增） | 纯函数 `build_sub_level(daily_result, sub_result)` 产出联动结论；不做 IO。 |
| `app/schemas/chan.py` | 新增 `SubLevelResponse`（日线倾向及文案、30 分钟近期信号列表、verdict、verdict_label、detail）。 |
| `app/api/v1/chan.py` | 新增 `GET /api/v1/chan/sub-level?symbol=`：拉日线（沿用现有窗口锚定）+ 30 分钟，各跑一次分析，返回联动结论。独立接口，不改 `/chan/analysis`。 |
| `app/services/signal_radar/` | 仅对最终入榜的候选补算次级别结论，气泡数据新增可选字段 `sub_level_verdict`（旧版 App 忽略未知字段）。 |
| iOS `DeepAlphaChan` | 分析详情页新增「次级别确认」卡片（异步加载，失败不影响页面）；信号雷达共振气泡加小标记。模型字段均为可选，兼容后端未部署的情况。 |

## 错误处理

- 30 分钟取数失败、数据不足（笔不足无法分析）→ `verdict="unavailable"`，接口仍返回 200，日线结论照常给出。
- 信号雷达补算失败的个别候选 → 该候选 `sub_level_verdict` 为空，不影响榜单。

## 测试

- `sub_level.build_sub_level` 纯函数单测：覆盖五种 verdict 与「同时有买卖点取最新」。
- adapter 时间格式：同一天多根 30 分钟 K 线时间不冲突、日线仍为日期格式。
- kline 30 分钟解析：FMP/Yahoo 响应解析与时区换算（用构造响应做单测，不打网络）。
- 真实行情端到端核对：美股、港股、A 股各一只。

## 实施顺序

1. 数据层 + 时间格式
2. 联动判定 + 接口
3. 信号雷达接入
4. iOS 卡片与雷达标记（需重新发版才对用户可见）
