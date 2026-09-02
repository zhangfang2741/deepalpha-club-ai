# 缠论 App 截图即分享 — 设计

**日期**：2026-09-02
**取代**：`2026-09-01-chan-share-card-design.md` 中的「精排分享卡」路线（该 spec 的二维码与中转页部分继续有效）

## 目标

用户在 App 内截图后，自动生成一张「品牌头 + 原界面截图 + 免责条」的分享图并弹出预览，
让用户先看清要发什么再发。同时保留主动分享按钮，并给全屏图表页让出被壳子占掉的高度。

解决三个已知问题：

1. 现有流程点分享按钮直接弹系统面板，用户没见过图就发出去了（盲发）。
2. 分享卡二维码只有 56pt，「扫码下载」提示 11pt，和 10pt 免责声明挤在一起，没有视觉层级。
3. 全屏图表页顶部的图层开关（分型/笔/线段/中枢）占掉 42pt，横屏下屏幕总高才 390pt 左右。

## 一、成图构图

```
┌────────────────────────────┐
│ ◈ DeepAlpha 缠论    ┌────┐ │  品牌头 88pt
│   缠论结构 自动标注   │▓▓▓▓│ │  二维码 64pt
│                     └────┘ │
├ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┤  虚线分隔
│                            │
│      用户界面原样截图        │  所见即所得，不含状态栏
│                            │
├────────────────────────────┤
│ 算法自动生成，不构成投资建议  │  免责条 24pt
└────────────────────────────┘
```

**宽度**跟随截图实际宽度，不写死 375 —— 全屏图表页是横屏，截出来是横图。

**Slogan「缠论结构 自动标注」**只陈述功能。分享图会脱离 App 语境传播，
不能出现「先机」「收益」这类暗示性措辞。

**免责条不可省。** 富途的分享图没有这条，但本 App 明确输出一二三类买卖点信号，
图被当成荐股截图转发时，这行字是唯一还跟着图走的风险说明。用户截屏时未必滚动到了
结果页底部那行 `compactDisclaimer`，所以必须由品牌层无条件补上。

## 二、模块划分

| 文件 | 动作 | 职责 |
|---|---|---|
| `Share/ScreenshotDetector.swift` | 新增 | 监听截图通知 + 防抖，暴露 `.shareOnScreenshot()` modifier |
| `Share/WindowCapture.swift` | 新增 | 截当前 keyWindow 成 `UIImage` |
| `Share/ShareBanner.swift` | 新增 | 品牌头与免责条两个 SwiftUI 视图 |
| `Share/ShareLayout.swift` | 新增 | 纯几何计算，不依赖 UIKit，唯一可自动化测试的一层 |
| `Share/ShareComposer.swift` | 新增 | 按 `ShareLayout` 的矩形把三块绘成最终图 |
| `Share/SharePreviewSheet.swift` | 新增 | 底部预览弹窗 |
| `Share/ShareCardView.swift` | 删除 | 精排卡路线废弃 |
| `Share/ShareCardRenderer.swift` | 瘦身 | 仅保留 `shareText` 与 `ShareSheet` |
| `Share/QRCode.swift` | 不变 | 已支持任意边长与缓存 |
| `Views/Analysis/ResultDetailView.swift` | 改 | 接入新流程，分享按钮改走同一路径 |
| `Views/Analysis/ChartFullscreenView.swift` | 改 | 移除 `LayerToggles`，重算 `chromeHeight` |
| `Views/Learn/LearnTabView.swift` | 改 | 挂 `.shareOnScreenshot()` |

`LayerToggles`（在 `ChartSection.swift`）本身保留，竖屏结果页仍在用。

**数据流**：

```
截图通知 / 分享按钮
      ↓
WindowCapture.capture() -> UIImage?
      ↓
ShareLayout.compute(screenshotSize:) -> 各部分矩形（纯几何，可测）
      ↓
ShareComposer.compose(screenshot:) -> UIImage
      ↓
SharePreviewSheet（预览 + 保存相册 + 分享）
      ↓
ShareSheet(UIActivityViewController)
```

各模块只经 `UIImage` 通信，`ShareComposer` 不关心图哪来的，因此可以喂假图做 Preview 与单测。

## 三、截图捕获

iOS 不提供读取用户所截图片的 API，`userDidTakeScreenshotNotification` 只告知
「刚发生了截图」，不含图像。因此由 App 在收到通知时对当前 window 自截一张，
内容与用户所截一致，**唯一差别是没有状态栏**（状态栏属系统独立 window）。
富途的分享图同样不含状态栏，可佐证此路径。

取 window：

```swift
UIApplication.shared.connectedScenes
    .compactMap { $0 as? UIWindowScene }
    .first { $0.activationState == .foregroundActive }?
    .keyWindow
```

渲染优先 `drawHierarchy(in:afterScreenUpdates: false)`，失败降级 `layer.render(in:)`。
`afterScreenUpdates: false` 取已渲染内容，更快，且避免在通知回调里触发一次重排。

两者都失败则**静默放弃**，不弹错误框：用户只是截了个图，为一个他没主动发起的功能报错很打扰。

## 四、触发入口与监听范围

两条入口并存，共用同一条渲染与预览路径：

- **截图**：被动入口，「递到手边」。
- **分享按钮**：主动入口，保留在结果页导航栏。很多用户没有截图习惯，去掉会直接损失这部分分享。

**挂 `.shareOnScreenshot()` 的页面**：分析结果页、全屏图表页、学习页。

**不挂**：`ProfileView`（含邮箱地址）、`LoginView`、`RegisterView`、
`ForgotPasswordView`、`PaywallView`。在这些页面截图会把账号信息拼进分享图。

**防抖**：0.5 秒内的重复通知忽略；预览弹窗已在展示时不再重复弹出。

截图与拼图全程在本地完成，不上传任何数据。

## 五、全屏页瘦身

`ChartFullscreenView` 移除 `LayerToggles`。图层状态沿用进入全屏前在竖屏结果页的设置，
全屏内不可改 —— 全屏的用途是尽可能大地看图。

`chromeHeight` 由 132 降至 90（省下开关行约 34pt 与一个 8pt 间距），差额全部给图表。

## 六、Info.plist

`NSPhotoLibraryAddUsageDescription` 已在 `ios/DeepAlphaChan/Resources/Info.plist` 中声明，
「保存到相册」直接可用，无需新增权限项。截图检测本身不需要任何权限声明 ——
它不读取相册，只接收一个系统通知。

## 七、验证

**自动化**（`ios/Tests/`）：

本工程没有 XCTest target —— 工程用 `PBXFileSystemSynchronizedRootGroup` 组织，
手工改 `project.pbxproj` 加 target 风险大于收益（见 `run-dictation-judge-tests.sh` 注释）。
既有做法是用 `swiftc` 直接编译真实源文件 + 断言脚本，本设计沿用。

该模式在 macOS 命令行下编译，**UIKit 不可用**。因此把尺寸计算抽成独立的
`ShareLayout`：纯函数，只依赖 CoreGraphics 的 `CGSize`/`CGRect`，不碰 UIKit。
可测的是它，`ShareComposer` 只负责按 `ShareLayout` 给出的矩形实际绘制。

- 输出宽度等于截图宽度；输出高度 = 品牌头 + 截图 + 免责条。
- 横图（横屏截图）与竖图各跑一次，确认品牌头随宽度自适应而非写死 375。
- 截图极窄或极宽时各部分矩形不重叠、不出现负高度。

**SwiftUI Preview**：`ShareBanner` 与 `SharePreviewSheet` 喂一张假截图目视确认排版。

**真机手动**（自动化覆盖不到）：

- 结果页截图 → 预览弹出 → 分享到微信，确认图完整、二维码可扫。
- 全屏横屏截图 → 确认横图构图正常。
- 「我的」页截图 → 确认**不**弹预览。
- 连续快速截图两次 → 确认只弹一次。

## 七、边界情况

- **截图失败**：静默放弃，不打扰用户。
- **超长页面**：只截当前可视区域，不做滚动长截图。用户看到什么就分享什么，与所见即所得的前提一致。
- **主题**：App 强制深色（`DeepAlphaChanApp.swift` 的 `.preferredColorScheme(.dark)`），
  品牌头与免责条直接用 `Theme` 深色值，不需要处理浅色分支。二维码固定白底黑码，
  识别率优先（见 `QRCode.swift` 注释）。
- **预览弹窗展示时再次截图**：防抖逻辑拦截，不套娃。
- **相册权限**：「保存到相册」首次触发系统授权；拒绝后提示一次，不反复弹。

---

## 附：实施过程中的设计演进（2026-09-02 终版）

按本 spec 首版实施后，真机反馈与代码审查推动以下演进，以本节为准：

1. **截图卡片化**：spec 首版的三块紧贴布局中，品牌头(#141A24)与截图顶部
   (#0B0E14)色差过小、糊成一片。改为截图内嵌卡片：左右各留 12pt(`outerPadding`)、
   上下各留 12pt(`gap`)、圆角 10pt，品牌头与免责条通栏，整图铺 `Theme.background` 底色。
2. **底部 TabBar 不入图**：`WindowCapture` 检测可见 TabBar（SwiftUI TabView 底层是
   UITabBarController）并裁掉；判定保守——拿不准不裁（误裁切内容，漏裁只多一条栏，代价不对等）。
3. **按钮输出整页长图**：详情页分享按钮不再截当前窗口，而是把页面内容抽成
   `pageContent(isStatic:)` 用 `ImageRenderer` 渲染整页长图。静态模式去分段切换器
   （UISegmentedControl 是 UIKit 桥接，ImageRenderer 拍不平会留空白；且静态图里
   切换无意义），两段全铺。渲染 scale 按「单张位图 ≤35MB」预算连续反推
   `clamp(1...3, √(预算/(宽×高)))`，量高用 0.25x 预渲染。
4. **全局仲裁**：各 modifier 自判可见性挡不住子视图 sheet（GlossaryLink 术语弹窗
   抢 presenter，`previewItem` 卡死在非 nil，本页分享静默失效）。改为
   `ScreenshotShareCoordinator` 进程级栈仲裁：仅栈顶响应 + 全局防抖。
   挂载点 ID 必须 `@State`（`let` 会随 body 重算变号，截一次后永久失效）。
   隐私页（登录/注册/找回/付费墙/我的）与术语弹窗挂 `suppressScreenshotShare()`
   显式吞事件，隐私边界从推断变为声明。
5. **分享文案**（`ShareText.share`）末尾带免责语：分享面板传图+文时微信等常只取其一，
   纯文字那侧必须有风险说明。
6. **保存到相册**：`.addOnly` 权限 + `PHPhotoLibrary` async API，三态如实提示
   （成功/权限被拒+跳设置/失败），防连点，成功后半秒自动关闭预览。

## 附：真机验证清单

- [ ] 结果页截图 → 预览弹出，卡片化构图正常，无 TabBar
- [ ] 详情页分享按钮 → 整页长图，含形态分析+买卖点两段，无分段切换器
- [ ] 微信收到分享（图被压缩后）二维码仍可扫 —— 决定二维码是否需加大
- [ ] 图例点「笔」→ 术语弹窗上截图 → 不弹预览；关掉术语后再截图 → 正常弹出（协调器）
- [ ] 预览开着时再截图 → 不套娃
- [ ] 连续两次快速截图 → 只弹一次
- [ ] 进「学习」Tab 再回「分析」Tab 截图 → 只弹分析页内容
- [ ] 分析 Tab → 结果页 → 切「我的」Tab → 截图 → 什么都不发生（隐私边界，最高优先）
- [ ] 我的/登录/注册/找回/付费墙截图 → 均不弹预览
- [ ] 登录前「先看看缠论入门」sheet 里截图 → 不弹预览
- [ ] 全屏图表页（横屏）截图 → 横图构图正常、图表比改前高（图层开关已移除）
- [ ] 从结果页进全屏 → 退出 → 再截图 → 仍能正常弹出
- [ ] 拒绝相册权限后保存 → 提示去设置，不谎报成功；允许后保存 → 相册确实有
- [ ] 英文界面：品牌头/免责条/保存按钮/授权弹窗均为英文，SE 宽度下不截字
- [ ] 分享到微信：确认微信最终收到的是图还是文字（决定文案策略是否需再调）
