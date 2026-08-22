# 缠论 iOS 分析页布局重构与学习模块

日期：2026-08-22
状态：设计已确认，待实施

## 背景与目标

缠论 App 现在只有一个页面 `ChanDashboardView`，把所有内容堆在一条竖直滚动流里：

```
查询栏（搜索 + 日线/周线 + 起止日期 + 分析按钮，约占首屏 1/3）
额度条（免费用户）
免责声明
图层开关（分型/笔/线段/中枢/买卖点）
K 线图
图例
信号面板（当前结构 / 操作倾向 / 买卖点 / 待确认结构 —— 4 张卡）
结构 GAP 分析（含多行文本输入 + AI 结果）
```

问题是查询表单在分析完成后仍然占据首屏三分之一，把核心的图表挤到折叠线以下；
结论、买卖点、GAP 三类性质不同的内容首尾相连，读任何一项都要长距离滚动。

本次改造：

1. 底部 TabBar 拆成「分析 / 学习 / 我的」三页
2. 分析页内部重组：查询条可折叠、图表占主并支持全屏与横屏、结论用分段控件切换
3. 新增学习模块（缠论概念教程），并让分析结果里的术语可点击跳转到对应词条

## 架构

### 一、导航

根视图从「登录态决定单页」改为「登录态决定单页 / TabView」：

```
RootView
└─ 已登录 → MainTabView
              ├─ 分析  AnalysisTabView
              ├─ 学习  LearnTabView
              └─ 我的  ProfileView
```

`ProfileView` 由 toolbar 的 sheet 提升为 Tab。它承载登出与删除账号——删除账号是
App Store 5.1.1(v) 的硬性入口要求，藏在右上角图标里不利于审核也不利于用户找到。

提升时有三处连带清理，漏掉会留下死代码或重复入口：

- 去掉 `ProfileView` 内部依赖 `@Environment(\.dismiss)` 的关闭按钮
- 删掉分析页 toolbar 上的 `person.circle` 按钮与 `showSettings` 状态
- 删掉分析页的 `.sheet(isPresented: $showSettings)`

Pro 皇冠入口保留在分析页 toolbar，不进 TabBar。

### 二、分析页拆分

`ChanDashboardView`（253 行）目前同时负责：查询表单、图层开关、图例、三种状态视图
（loading / error / empty）、免费额度门禁。拆成四个文件：

| 文件 | 职责 |
|------|------|
| `AnalysisTabView.swift` | 编排、门禁逻辑（`triggerAnalysis`）、三种状态视图 |
| `QueryBar.swift` | 查询条，展开与折叠两种形态 |
| `ChartSection.swift` | 图层开关 + 图表 + 图例 + 全屏入口 |
| `ResultSegments.swift` | 分段控件 + 三段内容的分发 |

**查询条双形态**是本次布局改善的关键。分析成功后自动折叠为一行摘要
（`AAPL · 日线 · 05-22 ~ 08-22` + 齿轮），点击展开回完整表单。展开态由
`@State private var isQueryExpanded` 控制，初值 `true`（未分析时展开），
分析成功后置 `false`。用户主动点齿轮可再次展开。

**分段控件三段**，把现在纵向堆叠的 5 张卡按性质分开：

| 段 | 内容 | 来源 |
|----|------|------|
| 结论 | 当前结构、操作倾向、待确认结构 | `SignalPanelView` 拆出 |
| 买卖点 | 买卖点列表 | `SignalPanelView` 拆出 |
| GAP | 结构 GAP 分析 | `GapAnalysisView` 原样 |

`SignalPanelView`（150 行）随之拆成 `ConclusionSection` 与 `SignalListSection`
两个视图，共用的标签/配色辅助函数（`trendLabel`、`biasColor`、`strengthLabel` 等）
抽到 `SignalFormatting.swift`。

### 三、图表全屏与横屏

图表右下角加全屏按钮，`fullScreenCover` 打开 `ChartFullscreenView`：沉浸式显示图表，
保留图层开关，右上角关闭。

**横屏支持会牵动全局，这是本次风险最高的一处。** 现状：

```
UISupportedInterfaceOrientations        = [Portrait]           # iPhone 只有竖屏
UISupportedInterfaceOrientations~ipad   = [全部四个方向]
```

要让全屏图表能横过来，必须给 iPhone 放开 `LandscapeLeft` / `LandscapeRight`，
但这会让**所有页面**都能旋转。所以同时引入方向锁：

- 新增 `AppOrientation`（`ObservableObject`），持有当前允许的方向掩码，默认 `.portrait`
- 新增 `AppDelegate`，实现 `application(_:supportedInterfaceOrientationsFor:)` 返回该掩码
- `DeepAlphaChanApp` 用 `@UIApplicationDelegateAdaptor` 挂上
- `ChartFullscreenView` 出现时把掩码设为 `.allButUpsideDown`，`onDisappear` 还原为
  `.portrait`，并用 `requestGeometryUpdate`（iOS 16+，本项目 deployment target 17.0）
  把界面转回竖屏

还原这一步不能漏：漏了的话用户从横屏全屏退出后，整个 App 会卡在横屏。

### 四、学习模块

**内容存 `Resources/Lessons/lessons.json`，不硬编码进 Swift。** 改文案不必碰代码，
也不必理解 SwiftUI。

```swift
struct LessonArticle: Identifiable, Codable {
    let id: String        // "pivot"、"divergence"…… 同时作为术语跳转的锚点
    let title: String
    let summary: String   // 列表页显示的一句话
    let body: String      // Markdown
}
```

首版 8 篇：K 线包含处理、分型、笔、线段、中枢、背驰、三类买卖点、走势级别。
**内容是通行解读，不保证符合任何特定交易体系**，交付后由使用者按需修改。

页面：

- `LearnTabView`：列表，显示 title + summary
- `LessonDetailView`：详情，Markdown 用 SwiftUI 原生
  `AttributedString(markdown:)` 渲染，不引第三方库
- `LessonStore`：启动时读 JSON，按 id 建索引；解析失败时返回空列表并记日志，
  不让 App 崩

Markdown 渲染的限制要说明：`AttributedString(markdown:)` 只支持行内语法
（粗体、斜体、链接、行内代码），不支持列表和标题的块级渲染。所以 `body` 的写法
约定为「短段落 + 空行分隔」，用 `•` 手动起项目符号，不用 `#` 和 `-`。

### 五、术语联动

- `GlossaryIndex`：维护「术语文本 → lesson id」映射
- `GlossaryLink`：把一段术语文本渲染成可点，点击以 sheet 弹出 `LessonDetailView`

接入点：图例的 5 个术语（笔、线段、中枢、顶分型、底分型），信号卡里的
「背驰」「中枢」「一买/二买/三买」。

术语在 `GlossaryIndex` 里查不到时，`GlossaryLink` 退化为普通文本，不可点也不报错——
词条还没写完时界面不该出现死链。

### 六、两个合规元素的去处

- **额度条**：留在分析页顶部。它是付费转化点，位置不动。
- **`DisclaimerBanner`**：分析页底部压成一行小字，完整版放「我的」页。
  App Store 要求投资类内容的免责声明可见，不能删。

## 数据流

学习内容是静态的，启动时一次性加载：

```
App 启动 → LessonStore.load() 读 Bundle 里的 lessons.json
        → 解析为 [LessonArticle]，按 id 建字典
LearnTabView       → 列表渲染
GlossaryLink 点击  → GlossaryIndex 查 id → LessonStore 取文章 → sheet 弹详情
```

分析流程本身不变，只是渲染位置变了：`ChanViewModel` 一行不改。

## 错误处理

- `lessons.json` 缺失或解析失败：`LessonStore` 返回空列表，学习页显示
  「教程内容加载失败」，其余功能不受影响
- 术语在索引里查不到：`GlossaryLink` 退化为普通文本
- 图表全屏页退出时方向未能还原：`onDisappear` 里无条件还原，不依赖任何成功回调

## 测试

这个 target 没有 XCTest，无法写单元测试。可测的纯逻辑（`GlossaryIndex` 查找、
`LessonStore` 解析）抽成不依赖 UI 的结构体，将来补测试 target 时可直接覆盖。

验证手段：

1. `xcodebuild` 真机 + 模拟器编译
2. 模拟器截图核对四个界面：分析页（查询展开）、分析页（查询折叠 + 分段）、
   学习列表、词条详情
3. 手工测试矩阵，重点是方向锁：进全屏 → 转横屏 → 退出 → 确认回到竖屏且其余页面
   不可旋转

## 明确不做

- 不改后端
- 不动 `ChanChartView`（549 行绘图逻辑），只在外面套全屏容器
- 不做教程内容的服务端下发与后台编辑
- 不做 iPad 专门布局（现状是 iPhone 布局拉伸，本次不改变）
- 不引入第三方 Markdown 渲染库

## 实施顺序

1. 学习模块（内容模型 + JSON + 两个页面）——完全独立，不碰现有代码
2. 术语联动（`GlossaryIndex` + `GlossaryLink`）
3. TabBar 导航 + `ProfileView` 提升为 Tab
4. 分析页拆分（`QueryBar` 折叠、`ChartSection`、`ResultSegments`）
5. 图表全屏 + 方向锁（风险最高，放最后，前面都稳了再动全局配置）

每步独立提交，每步都能编译通过。
