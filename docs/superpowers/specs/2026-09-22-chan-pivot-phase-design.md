# 缠论详情页「进度主线」（pivot_phase）设计

日期：2026-09-22
状态：设计已确认，待实施

## 背景与目标

用户参考一份产品同事出的 UI mockup（缠论详情页・进度主线）提出改版需求：详情页
的「整体分析」段目前只陈述形态事实（当前状态大白话 + 加权依据 + 结构统计），
用户点进详情真正想知道的是两件事——**现在走到缠论标准流程的哪一步**，以及**为
什么**。mockup 在此基础上提出两处新内容：

1. 左屏（已实现主线）：当前状态卡片里插入「走到哪一步」进度条——阶段徽标 +
   已完成/待确认 checklist + 一行「因为」原因 + 回抽结果的分支说明；卡片末尾
   新增「走势」标签（上涨趋势 / 可能转折向下 / 中枢依次抬高）。
2. 右屏（提案，待实现）：点阶段徽标弹出「阶段讲解」层——标准五步阶梯（中枢
   形成→中枢震荡→离开段→回抽确认→背驰转折）、当前处于哪一步、这一步为什么
   关键、现在满足到哪了。

调研代码后发现两个关键事实：

- **中枢 ZG/ZD/GG/DD/起止时间、当前价格已经暴露**（`PivotOut` / `merged_candles`
  最后一根），mockup 里的具体数值可以直接复用，不用新增。
- **没有任何现成字段等价于 mockup 要的五步进度**。`walk_type`（依中枢排布判定
  上涨/下跌/盘整）、`trend_outlook`（延续 vs 转折）、`narrative.phase`（大白话
  形态标签）是三套互相独立、口径不同的分类体系，都不是"中枢生命周期走到第几
  步"。`narrative.py` 明确写着设计原则是"只描述现状，不预测"，而 mockup 的
  「回抽不进中枢→确认三买 / 回抽跌回中枢→回到震荡」是条件式分支文案，需要
  确认这是否与"不预测"原则冲突。

跟用户讨论后确认：这类分支文案描述的是**规则本身在两种已定义结果下分别是什么
（真值表），不是对未来走势的主观预测**，可以用已有的中枢/笔/背驰结构做纯规则
判定，不违背"不预测"原则。因此决定新增一个后端状态机字段 `pivot_phase`，一份
设计覆盖前后端，按「先后端、再 iOS」分两阶段实施。

## 一、后端：`pivot_phase` 状态机

### 输入（全部复用已有计算，不新增任何几何/背驰判定逻辑）

- `stroke_pivots` / `segment_pivots`：含 `zg/zd/gg/dd/start_time/end_time/level/elements`
- `strokes`：含 `direction/start_price/end_price/confirmed`
- `divergences`：与 `strokes` 一一对应的背驰标记
- `signals.py` 里已有的 `_post_pivot_strokes` 窗口逻辑（中枢「离开段」笔窗口）

### 当前锚定中枢

取 `stroke_pivots ∪ segment_pivots` 中 `end_time` 最新的一个；并列时取线段级——
与 `walk_type` 判定"线段优先、笔级兜底"的既有原则保持一致，全仓库只有一处判断
"当前该看哪个中枢"的口径。

### 阶段判定

**关键实现细节**（调研 `test_signals.py::test_buy2_fires_when_pivot_absorbs_breakout_and_retrace`
才发现，会用一整版覆盖设计初稿里过于简化的假设）：`pivot.py` 的中枢延伸判定是
"只要笔与 `[ZD, ZG]` 有任意重叠就吞并"，比"完全落在区间内"宽松得多——真正的
突破笔/回踩笔只要还有一点价格重叠，也会被吞并进 `pivot.elements`，不会自然出现
在 `end_time` 之后。`_post_pivot_strokes` 因此要把 `pivot.elements[3:]`（中枢自己
吞并的延伸段）连同真正在 `end_time` 之后的笔一起拼成 `post`，`generate_buy2/3_signals`
才能从 `post` 里配对出真正的突破笔+回踩笔。

这意味着 `post` 非空**不能**直接当作"已出现突破"的信号——`post` 里可能全是
"仍在震荡、没有真正突破"的延伸笔。阶段判定必须复用 `generate_buy2/3_signals`
同一套"突破笔跨越边界"判据，在 `post` 里从头找**第一对**满足条件的
（突破笔, 回踩笔），而不是简单看 `len(post)`：

| phase | 判定条件 |
|---|---|
| `none` | 笔数 < 3，或没有有效中枢（结构未成形，与 `narrative` 的隐藏条件一致） |
| `pivot_forming` | `post` 中找不到任何一笔满足"突破笔"条件（起点在中枢内、终点越过 ZG 或 ZD），且中枢恰好是最初 3 段构成 |
| `pivot_oscillating` | 同上找不到突破笔，但中枢已吞并了更多段（`elements` > 3），或曾经出现过 `back_to_range`（假突破退回） |
| `leaving` | `post` 中找到了满足条件的突破笔，但其后紧跟的一笔方向不对/或它是 `post` 最后一笔（回抽笔尚未出现） |
| `retrace_confirmed` | 找到"突破笔 + 紧邻的反向回抽笔"这一对，取其 `outcome`（见下），且 `outcome ∈ {type2, type3}` |
| `divergence_turn` | `retrace_confirmed` 之后，`post` 中该配对**之后**的笔里，出现与突破方向同向、且 `divergences.is_diverged` 的笔（对应已生成一类买/卖点） |

`outcome` 三取一，判据与 `generate_buy2_signals`/`generate_buy3_signals`
（`app/services/chan/signals.py`）完全一致，不再另起一套数字：回踩守住对侧边界外
→ `type3`；落在 `[zd, zg]` 内未破对侧边界 → `type2`；穿破对侧边界 → `back_to_range`
（视为回退到 `pivot_oscillating`，用于给"假突破"一个去处，不新增第 7 个 phase）。

判定条件全部由既有结构的静态几何关系推出，不引入新的预测规则；实现时**独立
重写**这套"找第一对突破+回踩"的判据（不直接改 `signals.py`），原因见下方
"与 signals.py 的关系"。`confirmed` 字段复用回抽笔 `.confirmed` 的既有语义
（是否仍可能因右侧不确定性变化）。

### 与 signals.py 的关系（重要：不重构 signals.py）

`pivot_phase.py` 需要的"找第一对突破+回踩"逻辑，和 `generate_buy2/3_signals`/
`generate_sell2/3_signals` 里的逻辑本质相同，理想情况应该抽成共享函数复用。
但 `signals.py` 是 CLAUDE.md 明确标注"每条不变量都有单元测试 + 随机模糊护栏"
的高风险模块（历史上曾因为过度收紧/重写吞并逻辑出过真实回归，如 FIG 一买被
整段抹掉的教训），本次改动时间/精力有限、且核心目标是 iOS 详情页而非
signals.py 重构。因此本次**在 `pivot_phase.py` 里独立实现一份等价的判据**
（~15 行，允许和 `signals.py` 有少量重复），不改动 `signals.py` 一行代码，
把回归风险限制在新文件内。

为保证两处判据不会悄悄跑偏，`test_pivot_phase.py` 里加一个交叉验证测试：用
`test_signals.py` 里已经验证过的真实吞并场景（`find_stroke_pivots` 产出的
真实中枢 + 突破/回踩笔），同时断言 `generate_buy2_signals`/`generate_buy3_signals`
产出的信号类型，与 `pivot_phase` 判定出的 `outcome` 一致。后续如果要抽共享
函数消重复，这个测试能直接复用来验证重构没有改变行为。

### 分支文案（仅 `leaving` 阶段给出）

`leaving` 阶段的回抽结果尚未发生，给出规则本身的三种可能结果（真值表，不是
预测）：

- 回踩守住对侧边界外 → 确认三买/三卖（`type3`，最强）
- 回踩落在中枢内未破边界 → 确认二买/二卖（`type2`，中枢升级但弱于三买/三卖）
- 穿破对侧边界 → 假突破，回到中枢震荡（`back_to_range`）

### API 新增字段

挂在 `ChanAnalysis` 上，与 `narrative` / `recommendation` 平级：

```text
pivot_phase: {
  phase: "none" | "pivot_forming" | "pivot_oscillating" | "leaving"
       | "retrace_confirmed" | "divergence_turn",
  phase_label: "向上离开中枢",              # 人话标签，含方向
  direction: "up" | "down" | null,
  pivot: { zg, zd, start_time, end_time, level },   # 复用 PivotOut
  checklist: [ { label, detail, state: "done" | "pending" } ],
    # 固定生成规则：
    #   第 1 条「形成中枢」永远 done（能算出 pivot_phase 就说明中枢已存在）
    #   若 phase 不是 pivot_forming，追加一条「当前 phase 的 phase_label」done
    #   最后追加一条「phase 的下一步」pending（如 leaving 的下一步是回抽确认；
    #     divergence_turn 已是终态，不追加 pending 行，checklist 只有 2 条）
  reason: "现价 392.16 已站上 ZG 388.00，最新向上笔离开了中枢区间。",
  confirmed: true,
  branches: [ { outcome: "type2" | "type3" | "back_to_range",
                condition_label, result_label } ],   # 仅 leaving 阶段非空
  stage_guide: {
    current_index: 0..4,
    steps: [ { key, title, detail } ]  # 固定 5 条，按 direction/pivot 数值插值
    why_it_matters: "离开段是缠论趋势能否延续的分水岭：...",
  }
}
```

`phase == "none"` 时该字段整体为 `null`（不返回空壳对象），前端按"字段不存在"
处理，与 `narrative` 现有的可选先例一致。

`stage_guide.steps` 的文案是"方向相关但内容固定"的模板句（如"三段重叠围出
X-Y"、"向上离开中枢，候选第三类买点"），复用现有字符串拼接风格生成，不是新的
判断逻辑，五步描述在所有股票间只有方向/数值不同、结构相同。

顺手把已有的私有方法 `_walk_type_label` / `_trend_outlook_label`（目前只用于拼
`summary`，未单独暴露）加进 `ChanAnalysis` 响应，字段名 `walk_type_label` /
`trend_outlook_label`——mockup「走势」标签行（上涨趋势 / 可能转折向下 / 中枢依次
抬高）就是这两个字段的文案，此前 iOS 端完全没有消费。

所有文案按现有 `lang` 参数走中英双语，句式风格对齐 `narrative.py` / `signals.py`。

### 测试

`tests/services/chan/test_pivot_phase.py`：覆盖全部 6 种 `phase` + 3 种 `retrace`
`outcome`，随机模糊测试保证阶段单调（不回跳），仅 `back_to_range` 可显式退回
`pivot_oscillating`。

## 二、iOS：详情页改版

### Model 扩展（`Models/ChanModels.swift`）

新增 `PivotPhase` 及嵌套结构 `PhaseChecklistItem` / `PhaseBranch` / `StageGuide`
/ `StageGuideStep`，均为 `Codable`，字段与后端 payload 一一对应。

`ChanAnalysis` 新增：
- `pivotPhase: PivotPhase?`（缺失/`none` 时为 `nil`）
- `walkTypeLabel: String?`
- `trendOutlookLabel: String?`

### `Views/Analysis/AnalysisSection.swift` 改版

在 `statusCard` 的「依据」`BulletList` **之前**插入「走到哪一步」区块：

1. 阶段徽标：`Chip`（含 ⓘ）显示 `pivotPhase.phaseLabel`，点击拉起
   `PivotPhaseGuideSheet`
2. 新组件 `PhaseChecklist`：遍历 `checklist`，`state == .done` 用勾选图标，
   `.pending` 用空心圆，`detail` 灰字
3. 一行「因为」文案：`pivotPhase.reason`
4. `branches` 非空时，复用 `BulletList` 的箭头列表样式渲染
   `"\(condition_label) → \(result_label)"`

卡片末尾、`structureStats` 之前新增「走势」`Chip` 行：`walkTypeLabel` +
`trendOutlookLabel`（都非空时才渲染，同 `narrative` 的按需展示原则）。

`pivotPhase == nil` 时「走到哪一步」区块与走势标签整体不渲染，卡片退化为改版前
样式——不引入新的空态占位。

### 新增 `Views/Analysis/PivotPhaseGuideSheet.swift`

`.sheet`，由阶段徽标触发（呈现方式仿 `GlossaryLink`，内容是自定义 SwiftUI View，
不是 Markdown）：

- 顶部 Stepper：遍历 `stage_guide.steps`，`current_index` 对应项高亮"你在这"
- 「这一步为什么关键？」：`stage_guide.why_it_matters`
- 「现在满足到哪了？」：**直接复用** `pivotPhase.checklist`（图标换成 ✅/⚠️），
  不重复建模、不新增字段
- 底部静态提示文案（本地化字符串，如"点图上的笔/线段/中枢/买卖点，可逐个看它
  在当前图形怎么形成"）——图表联动点击查看结构不在本次范围内，只放静态文案

### 兼容与预览

- `Views/Analysis/PreviewMock.swift` 补一份带完整 `pivotPhase` 的 mock，供
  SwiftUI 预览和 UI 测试使用
- 分享长图（`ResultDetailView.pageContent(isStatic:)` / `PageSnapshot`）：
  `statusCard` 新增内容都是纯 SwiftUI 布局，无 UIKit 桥接控件，`ImageRenderer`
  可正常渲染，不需要像 `ResultSegments` 对分段控件那样做规避；`PivotPhaseGuideSheet`
  是交互层，长图不包含其内容

## 范围之外

- 图表联动（点击笔/线段/中枢/买卖点跳转到对应阶段讲解）——mockup 底部标注为
  "提案"，本次只做静态提示文案，交互留待后续单独设计
- 网页端 `/chan` 页的对应改版——后端字段设计已考虑跨端复用（`stage_guide` 等
  文案由后端生成而非硬编码进 iOS），但网页 UI 改版不在本次范围
- 二买/二卖信号本身的算法调整——`pivot_phase` 只是复用现有 `signals.py` 判定
  逻辑做状态归类，不改动买卖点生成算法

## 实施节奏

分两个阶段，阶段一验证通过（`make check` + 单元测试 + 手动跑几支真实标的核对
五个 phase 都能正确触发）后再开始阶段二：

1. **阶段一（后端）**：`pivot_phase` 状态机 + `walk_type_label`/`trend_outlook_label`
   暴露 + 单元测试
2. **阶段二（iOS）**：Model 扩展 → `AnalysisSection` 改版 → `PivotPhaseGuideSheet`
   新增 → mock 补充 → 真机/模拟器走查 golden path（五个 phase 各挑一支真实标的）
   与边界（`pivotPhase == nil`、`branches` 为空、`confirmed == false`）
