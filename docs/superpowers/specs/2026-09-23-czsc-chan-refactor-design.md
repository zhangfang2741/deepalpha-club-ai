# 缠论模块接入 czsc 重构设计

日期：2026-09-23

## 背景与动机

`app/services/chan` 目前是完全自研的缠论算法实现（约 3139 行，14 个文件），CLAUDE.md 中记录了大量已用随机模糊测试验证过的业务约束（前复权全链路、窗口锚定、分型/笔/线段/中枢结构不变量、背驰双过滤、二三类买卖点窗口限制等）。

问题不是"识别结果不准"，而是**代码本身难维护**：结构层和信号判定逻辑高度自研、耦合重，改一处容易牵连别处。目标是引入成熟开源库 [czsc](https://github.com/waditu/czsc)（Apache-2.0，PyPI 包 `czsc`，1,726 次提交，6.3k star，活跃维护）替换核心算法引擎，降低维护成本。

## 调研结论

- czsc 采用 **Rust + Python 混合架构**：分型/笔/中枢的核心算法已迁移至 Rust（通过 PyO3 暴露为 `czsc._native`），220+ 信号函数覆盖背驰/买卖点等信号判定。
- PyPI 最新版本 1.0.1，要求 Python ≥ 3.10，提供预编译 wheel（含 3.13），标准安装 `pip install czsc` 无需本地 Rust 工具链。
- czsc 是另一套独立的缠论解释体系（缠论本身无统一标准），其笔/中枢/买卖点判定逻辑与我们已验证的自研规则大概率不完全一致。
- czsc 定位偏实盘策略/回测框架（`CzscTrader`、`WeightBacktest`），信号走 event/signal 范式，和我们面向可视化展示（中枢阶段徽标、气泡强度、走势类型）的消费方式不完全对齐，需要适配层。

**内部依赖调研**（关键，决定了重构的安全边界）：

- `app/api/v1/chan.py` 的 `ChanAnalysisResponse`（`app/schemas/chan.py`）是纯 DTO，与 `ChanAnalysisResult` 内部 dataclass 解耦，是相对安全的对外契约边界。
- `app/services/signal_radar/service.py`、`app/services/watchlist_phases.py` 只消费 `analyzer.analyze()` 产出的**最终聚合字段**（`result.signals`、`result.pivot_phase`），未绕过 analyzer 直接调用底层结构识别函数。
- `app/core/langgraph/tools/chan_analysis.py`、`structure_gap.py`、`app/services/chan/gap.py`、`app/services/chan/replay.py` **直接遍历 `ChanAnalysisResult` 内部 dataclass**（`strokes`/`segments`/`pivots`/`divergences`）甚至私有函数（如 `pivot_phase.py` 的 `_post_pivot_strokes`），是高风险的绕过点，替换算法引擎后必须同步改造。

## 设计范围

### 全面替换：结构识别 + 信号判定

不做"只换底层引擎、业务层完全保留"的保守方案，而是**结构识别（分型/笔/线段/中枢）和买卖点信号判定都改用 czsc**（含背驰、一二三类买卖点），采用 czsc 自带的 signal 体系替代现有的双过滤背驰判断和买卖点窗口限制规则。这意味着放弃 CLAUDE.md 中记录的自研规则，最终图形表现会与现状不同——这是本次重构主动接受的代价，不是回归目标。

### 对外契约：保持 schema 不变，允许字段降级

`app/schemas/chan.py` 的 `ChanAnalysisResponse` 字段结构保持不变，前端、LangGraph tools 不用重新设计。czsc 输出在新增的适配层映射回现有字段；映不上的字段允许缺失/降级为 `None`，不强行凑数据、不为了对齐字段而扭曲 czsc 的原始语义。

### 买卖点信号引擎：独立模块，不和展示逻辑耦合

买卖点信号计算封装成独立 service 模块（`app/services/chan/czsc_signals.py`），只依赖 czsc 的结构识别结果，不感知 `stroke.py`/`pivot.py` 的展示逻辑，可独立单测（给定一段 K 线 → 断言买卖点列表），不需要拉通整个 `analyze()` 流程。

## 组件设计

| 文件 | 变化 |
|------|------|
| `app/services/chan/czsc_adapter.py`（新增） | 前复权后的 bars → czsc `RawBar` 输入 → 调用 czsc 引擎产出 `CZSC` 对象 → 转换回现有 `Fractal`/`Stroke`/`Segment`/`Pivot` dataclass 形状（字段名尽量对齐，映不上置 `None`） |
| `app/services/chan/czsc_signals.py`（新增） | 买卖点信号引擎，封装 czsc signal 体系，产出 `DivergenceResult`/`Signal` 形状的买卖点列表，独立于展示逻辑 |
| `fractal.py` / `stroke.py` / `segment.py` / `pivot.py` | 删除自研识别逻辑，改为调用 `czsc_adapter` |
| `divergence.py` / `signals.py` | 删除自研背驰双过滤/买卖点判定，改为调用 `czsc_signals` |
| `bias.py` / `narrative.py` / `pivot_phase.py` / `gap.py` / `replay.py` | 保留业务目标（多因子推荐、中文叙事、阶段状态机、结构缺口分析、历史回放），内部实现跟着新的 dataclass 形状重写 |
| `analyzer.py` | 编排顺序基本不变：`czsc_adapter` 拿结构 → `czsc_signals` 拿买卖点 → 喂给 `pivot_phase`/`narrative`/`bias` |
| `app/core/langgraph/tools/chan_analysis.py`、`structure_gap.py` | 同步改造以适配可能缺失的字段 |

## 实现顺序（分阶段验证）

1. **Spike（go/no-go 前提）**：`uv add czsc`，验证 Python 3.13 + Railway 部署环境能装上预编译 wheel；跑通最小 demo（喂一段真实 K 线，拿到笔/中枢）；验证 czsc 的 `CZSC` 对象（增量 `update()` 式）能否支持"在 warmup+可见窗口的完整序列上算完再裁剪"的窗口锚定方式，或需要改造成流式喂入。
2. **结构识别引擎**：实现 `czsc_adapter.py`，替换 `fractal/stroke/segment/pivot`，先让 `ChanAnalysisResponse` 中结构部分字段出数据（买卖点先留空），用几只熟悉的股票人工核对笔/中枢画得对不对。
3. **买卖点信号引擎**：实现 `czsc_signals.py`，替换 `divergence/signals`，人工核对买卖点标注。
4. **业务层收尾**：重写 `pivot_phase`/`narrative`/`bias`/`gap`/`replay`，改造 LangGraph tools。
5. **全量回归**：跑通 `tests/services/chan/`（预期大量失败，逐个决定删除重写还是调整期望值）+ 手工过一遍 `/chan`、`signal-radar`、`watchlist` 页面。

## 测试策略

- `tests/services/chan/` 中验证"自研算法不变量"的用例（分型间隔、笔首尾相连、线段吞没起点、中枢 ZG/ZD 规则、背驰双过滤、随机模糊护栏等）大部分会因换引擎失效，逐个决定删除重写（针对 czsc 实际行为定义新期望）或彻底移除，不批量 `skip`。
- `czsc_adapter.py`、`czsc_signals.py` 走 TDD：先写"给定一段真实 K 线，期望产出什么笔/中枢/买卖点"的用例，再实现适配逻辑。
- `pivot_phase`/`narrative`/`gap`/`replay` 的现有测试按新数据形状调整断言，业务目标不变。

## 风险与应对

1. **部署可行性**：czsc 是 Rust+PyO3 混合包，需在 spike 阶段确认 Railway 构建环境能装上预编译 wheel，装不上则方案不可行。
2. **窗口锚定兼容性**：czsc 的增量 `update()` 模式和现有"全量算完裁剪"方式可能不匹配，需在 spike 阶段验证。
3. **字段映射降级**：schema 字段映不上时前端/LangGraph tools 拿到 `None`，需过一遍消费方确认不会因空值报错崩溃（尤其 `chan_analysis.py`/`structure_gap.py`）。
4. **视觉结果变化**：czsc 的笔/线段/中枢/买卖点判定与现有实现不同，上线后图形表现会变化，这是主动接受的代价，需要在实际使用（盯盘核对）时对齐预期为"不一样"而非"更对"。

## 实施约定

- 本次改动在新分支上进行，不直接在 `master` 上开发。
- 遵循项目 TDD 迭代规则：新功能先写 failing test 再实现，每完成一个小功能即提交（小步提交）。
