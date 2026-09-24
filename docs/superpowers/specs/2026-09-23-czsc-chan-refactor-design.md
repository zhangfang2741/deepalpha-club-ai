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

## czsc 真实 API（调研自 PyPI 1.0.1 / GitHub master 的 `czsc/_native/__init__.pyi` 类型 stub）

核心算法已全部迁移至 Rust（`czsc._native`），以下是确认过的真实签名，供后续实现直接使用：

- `RawBar(symbol: str, dt, freq: Freq, open: float, close: float, high: float, low: float, vol: float, amount: float, id: int = 0)` —— 原始 K 线，`freq` 为 `Freq` 枚举（`Freq.D`=日线等）。我们的 `bars: list[dict]`（`time/open/high/low/close/volume`）里没有 `amount`（成交额），需要在 adapter 里置 0.0 或用 `close*volume` 近似。
- `CZSC(bars_raw: Sequence[RawBar], max_bi_num: int = 0, min_bi_len: int = 0)` —— 核心分析对象，构造时一次性喂入完整序列（不是必须流式 `update()`），属性：`fx_list: list[FX]`、`bi_list: list[BI]`、`zs_list: list[ZS]`（基于已完成笔计算的笔级别中枢）。
- `FX`：`symbol/dt/mark(Mark.G顶或Mark.D底)/high/low/fx/elements`。
- `BI`：`symbol/direction(Direction.Up/Down)/high/low/fx_a(起点FX)/fx_b(终点FX)/sdt/edt/power/length/change` 等。
- `ZS`：`bis(构成中枢的BI列表)/sdt/edt/zg/zd/zz/gg/dd`——`zg/zd/gg/dd` 字段名与我们自己的 `Pivot.zg/zd/gg/dd` 完全一致，映射成本低。
- `format_standard_kline(df: pd.DataFrame, freq: Freq | str) -> list[RawBar]`：要求 DataFrame 含 `dt/symbol/open/close/high/low/vol/amount` 八列；我们也可以不经 DataFrame，直接逐根构造 `RawBar`。
- `generate_czsc_signals` / `get_signals_config` / `derive_signals_config`（`czsc.traders`）：信号计算入口，`Signal` 对象字段为 `key/value/k1/k2/k3/v1/v2/v3/score`。**具体哪些信号函数对应背驰/买卖点，220+ 个信号函数编译在 Rust 里，没有可静态阅读的源码目录，必须在 spike 阶段实际安装后运行时探测**（如 `dir(czsc._native.signals)`、`parse_signal_doc`），不能凭文档猜测。
- **czsc 没有线段（Segment）对象**（详见上文组件设计的澄清），`bi_list`/`zs_list` 已是能拿到的最细粒度结构化输出。

## 组件设计

**重要澄清（调研发现，经过多轮验证）**：czsc（从 2024 年的纯 Python 版本 v0.9.69、到当前 1.0.1 的 Rust 版本、到官方案例索引 `docs/examples.md` "缠论核心"分组）**从未实现过"线段"对象**——`CZSC` 只暴露 `bi_list`（笔）/`zs_list`（笔级别中枢，直接由连续 3 笔的价格重叠区域计算，`zg/zd` 取最初 3 笔、`gg/dd` 随延伸更新，和我们自己的中枢规则概念一致）/`fx_list`（分型），没有 `seg_list`/`Segment` 之类的线段结构。czsc 处理"跨尺度结构"的方式是多周期联立（`BarGenerator`/`CzscTrader` 同时维护多个 `Freq` 各自的分型/笔/中枢），不是在同一周期内用特征序列算法拼出线段这个中间层。

**决定（2026-09-24 修订）：线段层保留自研实现，只换数据源；中枢改用 czsc 的。**理由：

- czsc 没有线段对象，但我们的 `segment.py`（特征序列算法）运行稳定、有完整测试，且被 `ChanAnalysisResult.segments/segment_pivots`、Next.js 与 iOS 前端的线段渲染、lessons.json 教学内容共同依赖——删掉它牵连面太大（前端两端 + 教学内容 + 旧版 App 兼容），收益却只是"少维护一个文件"。
- 中枢改用 czsc 的 `zs_list`（笔级别）：czsc 的 `ZS` 定义（`zg/zd` 取最初 3 笔、`gg/dd` 随延伸更新）与我们自己的中枢规则概念一致，替换无语义争议。
- 30 分钟"次级别确认"（大级别日线定方向、小级别找更精确买卖点）仍是**独立待办**，需要新接入一路 30 分钟盘中数据源，不在本次重构范围内。

| 文件 | 变化 |
|------|------|
| `app/services/chan/czsc_adapter.py`（新增） | 前复权后的 bars → czsc `RawBar` 输入 → 调用 czsc 引擎产出 `CZSC` 对象 → 把 `fx_list`/`bi_list`/`zs_list`（笔级别）转换回现有 `Fractal`/`Stroke`/`Pivot` dataclass 形状（字段名尽量对齐，映不上置 `None`） |
| `app/services/chan/czsc_signals.py`（新增） | 买卖点信号引擎，封装 czsc signal 体系，产出 `DivergenceResult`/`Signal` 形状的买卖点列表，独立于展示逻辑 |
| `fractal.py` / `stroke.py` / `pivot.py`（笔级别中枢部分） | 删除自研识别逻辑，改为调用 `czsc_adapter` |
| `segment.py`（线段） | **保留自研算法不变**，输入换成 `czsc_adapter` 转换后的 `Stroke` 列表 |
| `pivot.py`（线段级别中枢 `find_segment_pivots`） | **保留自研算法不变**，输入换为自研线段（其上游笔来自 czsc） |
| `divergence.py` | 笔级背驰改走 `czsc_signals`；`find_segment_divergences` **保留**（线段级背驰仍自研，消费自研线段） |
| `bias.py` / `narrative.py` / `pivot_phase.py` / `gap.py` / `replay.py` | 保留业务目标（多因子推荐、中文叙事、阶段状态机、结构缺口分析、历史回放），内部实现跟着新的 dataclass 形状重写（dataclass 形状不变，预计改动很小） |
| `app/schemas/chan.py` | **完全不动**（schema 全字段保持现状，包括 `segments`/`segment_pivots`，前端与旧版 App 无兼容问题） |
| `analyzer.py` | 编排顺序不变：`czsc_adapter` 拿分型/笔/笔级中枢 → 自研 `segment.py`/`pivot.py` 拿线段/线段级中枢 → `czsc_signals` 拿笔级背驰/买卖点 → 自研 `find_segment_divergences` 拿线段级背驰 → 喂给 `pivot_phase`/`narrative`/`bias` |
| `app/core/langgraph/tools/chan_analysis.py`、`structure_gap.py` | dataclass 形状不变，预计不需要改动（回归时确认） |

**因此前端（Next.js + iOS）不需要任何改动**，iOS 学习模块（lessons.json）的线段课程也保持现状。

## iOS 学习模块内容同步

`ios/DeepAlphaChan/Resources/{zh-Hans,en}.lproj/lessons.json` 是一套完整的缠论理论教程（9 节）。理论讲解不因本次重构改变（线段层保留了）。**可选后续增强**（独立待办，不阻塞本次重构）：每一节理论讲解之后补一段"本 App 具体怎么实现"，把理论和 App 实际采用的具体规则/阈值对应起来，全程不能出现 czsc 或任何第三方库名字——普通用户不需要知道我们用了什么开源库。此内容只能在结构识别引擎和买卖点信号引擎实际替换完成、真实行为确定之后再写。

## 实现顺序（分阶段验证）

1. **Spike（go/no-go 前提）**：✅ 已完成（见 `2026-09-23-czsc-spike-findings.md`）——`uv add czsc` 走预编译 wheel 安装成功，Python 3.13 环境可用；第二轮探测（2026-09-24）确认 `fx.mark == Mark.G` / `bi.direction == Direction.Up` 可直接比较（`.name` 给英文标识）、`BI.sdt/edt`/`FX.dt` 均为 `pd.Timestamp`、`generate_czsc_signals(bars, [dict...])` 返回逐 K 线信号字典（值格式 `v1_v2_v3_score`，如 `向上_延伸_任意_0`）。
2. **结构识别引擎**：实现 `czsc_adapter.py` 的完整映射（`fx_list`/`bi_list`/`zs_list` → `Fractal`/`Stroke`/`Pivot`，含 `MergedCandle` 重建与 `confirmed` 语义），`analyzer.py` 步骤 1-5 改接 czsc，线段层输入换源，用真实股票人工核对笔/中枢画得对不对。
3. **买卖点信号引擎**：实现 `czsc_signals.py`，替换 `signals.py` 买卖点判定，人工核对买卖点标注。

   **Phase 3 实际方案（2026-09-24，基于真实数据探测 + 阅读 czsc 源码后确定）**：
   - 信号选型（全部基于笔结构，不选纯 MACD 金叉死叉类，如 `tas_macd_first_bs_V221201` 实为零轴下金叉死叉节奏、不看笔结构）：
     一买/一卖 `cxt_first_buy/sell_V221126`（最近 5~21 笔，末笔创新低/新高且价差/量能/长度力度弱于前段关键笔）；
     二买/二卖 `cxt_second_bs_V240524`（W9T2：末笔终点分型与前 9 笔中 ≥2 个长笔终点分型价格重叠）；
     三买/三卖 `cxt_third_bs_V230318`（SMA34：前 5 笔构中枢，第 5 笔离开中枢且三个转折点均线同向）。
   - 用 `CzscSignals` 逐根推进（不回看未来），信号从「其他」切换为买卖点的那一刻，读取当时 `bi_list[-1]` 作为信号所属笔；Signal.time/price 取该笔终点，与图上笔端点对齐、`_mark_confirmations` 语义不变；按 (类型, 笔终点) 去重。
   - czsc 信号是持续多根的「状态」而非事件（`score` 恒为 0、不给强度），故强度由我们计算：一买/一卖 = 对应笔的背驰强度（沿用「一类强度只反映背驰幅度」），二/三类 = 最近中枢级别 + 余量（复用 `_type23_strength`）。
   - **背驰计算（`divergence.py`，MACD 面积 + DIF 双过滤）保留**：czsc 不输出面积比/DIF 比等可量化背驰指标，而推荐因子、走势展望、前端背驰字段依赖 `DivergenceResult`。即「是否构成买卖点」由 czsc 判定，「背驰有多强」仍由自研度量。
   - 面向用户的描述文案不出现 czsc 字样。
4. **业务层收尾与全量回归**：跑通 `tests/services/chan/`（逐个决定删除重写还是调整期望值），确认 LangGraph tools 无回归，手工过一遍 `/chan`、signal-radar、watchlist 页面。

（原第 5-7 步"前端同步/iOS 学习模块更新"随 2026-09-24 修订取消——线段层保留后，schema 与前端完全不变。）

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
