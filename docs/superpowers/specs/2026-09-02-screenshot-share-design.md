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
| `Share/ShareComposer.swift` | 新增 | 品牌头 + 截图 + 免责条拼成最终图 |
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

- `ShareComposer` 尺寸计算：输出宽度等于截图宽度；输出高度 = 品牌头 + 截图 + 免责条。
- 横图（横屏截图）与竖图各跑一次，确认品牌头随宽度自适应而非写死 375。
- `QRCode.image(for:side:)` 在品牌头所用的 64pt 下返回非 nil。

**SwiftUI Preview**：`ShareBanner` 与 `SharePreviewSheet` 喂一张假截图目视确认排版。

**真机手动**（自动化覆盖不到）：

- 结果页截图 → 预览弹出 → 分享到微信，确认图完整、二维码可扫。
- 全屏横屏截图 → 确认横图构图正常。
- 「我的」页截图 → 确认**不**弹预览。
- 连续快速截图两次 → 确认只弹一次。

## 七、边界情况

- **截图失败**：静默放弃，不打扰用户。
- **超长页面**：只截当前可视区域，不做滚动长截图。用户看到什么就分享什么，与所见即所得的前提一致。
- **深色/浅色主题**：品牌头与免责条用 `Theme` 色值，跟随 App 主题；二维码固定白底黑码，
  识别率优先（见 `QRCode.swift` 注释）。
- **预览弹窗展示时再次截图**：防抖逻辑拦截，不套娃。
- **相册权限**：「保存到相册」首次触发系统授权；拒绝后提示一次，不反复弹。
