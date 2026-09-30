# 量化研究 + 分析师评级 iOS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 缠论 App（`ios/DeepAlphaChan`）分析详情页新增三段分段「缠论结构 | 量化研究 | 分析师评级」，按设计文档 §4 实现量化研究三层下钻（首页 → 维度详情 → 指标详情 sheet）、五维图、方法说明页与分析师评级 Tab。

**Architecture:** 所有文案由后端按 `lang` 生成，App 只排版与画图。模型层（`Models/QuantResearchModels.swift`）严格对应后端 schema，用后端 golden JSON 做解码测试，守护前后端契约；五维图的几何与标签布局抽成纯函数（`FiveDimensionLayout`）单测；视图层按页面拆文件放 `Views/Quant/`、`Views/Analyst/`。工程用 Xcode 同步文件夹，新文件自动编译。

**Tech Stack:** SwiftUI（iOS 17+）/ async-await / swiftc 脚本测试（沿用 `ios/Tests/run-*.sh` 方式）

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `Models/QuantResearchModels.swift` | `QuantResearch` / `QuantDimension` / `QuantMetric` / `QuantMethodology` / `AnalystOverview` 等 Decodable |
| `Networking/QuantResearchService.swift` | `research(market:symbol:)`、`methodology()`、`analystOverview(market:symbol:)` |
| `ViewModels/QuantResearchViewModel.swift` | 两个 Tab 的加载状态（按需加载、按「市场+代码+语言」缓存） |
| `Views/Quant/QuantGradeStyle.swift` | 等级配色（红涨绿跌：A/B 红、C 灰、D/F 绿）与徽标 |
| `Views/Quant/FiveDimensionChart.swift` | 五维图（`FiveDimensionLayout` 纯函数 + 视图） |
| `Views/Quant/QuantResearchTab.swift` | 首页：综合等级窄卡 + 阶段标签 → 五张维度卡片（固定顺序，最高 / 最低高亮边框）→ 五维图 → 方法说明入口 → 免责 |
| `Views/Quant/QuantDimensionDetailView.swift` | 维度详情页：算式卡 + 按组列出指标行（本股 / 中位 / 差异 / 百分位条 / 等级） |
| `Views/Quant/QuantMetricSheet.swift` | 指标详情 sheet：定义 → 算式 → 板块分布条 → 位置推导 → 原始数据与时间 |
| `Views/Quant/QuantMethodologyView.swift` | 方法说明页 |
| `Views/Analyst/AnalystRatingTab.swift` | 评级分布、目标价、业绩预期 vs 实际、最近评级变动 |
| `Views/Analysis/ResultDetailView.swift`（改） | 顶部分段；「缠论结构」保持现状；分享长图只截当前分段 |
| `Resources/*/Localizable.strings`（改） | 新增静态标签的中英文 |
| `ios/Tests/QuantResearchTests.swift` + `run-quant-research-tests.sh` | golden JSON 解码、五维图布局不越界、等级配色 |

### Task 1: 模型与解码测试
用 `tests/fixtures/quant_research/golden_NVDA.json`（后端 golden）与分析师 fixture 生成的样例解码；断言 5 个维度、`accumulating` 状态、公式输入等字段。

### Task 2: 网络层与 ViewModel
路径 `/quant-research/{market}/{symbol}?lang=`、`/quant-research/methodology?lang=`、`/analyst-upgrades/overview/{symbol}?market=&lang=`；ViewModel 按 key 缓存，切 Tab 才加载，失败显示重试。

### Task 3: 五维图（纯函数布局 + 视图）
半径 = 百分位；实线本股、虚线板块中位（50）；不可用维度灰色虚轴「暂无」；标签按估算文字宽度放在画布内（草图曾出现左侧被裁）。单测：任意名称长度下标签矩形都在画布内。

### Task 4: 量化研究首页 + 维度详情 + 指标 sheet + 方法说明
按设计 §4；港股 / A 股显示后端 `status_note`；`insufficient_data` 显示说明。

### Task 5: 分析师评级 Tab
四张卡片；目标价轴从 min(现价, 最低) 到 max(现价, 最高)。

### Task 6: 接入 ResultDetailView + 本地化 + 编译 + 模拟器截图验收
`ios/Tests/build-check.sh` 编译通过；模拟器用 `-deepalphaDemo` 参数打开 NVDA 详情页，截取三个分段截图核对。
