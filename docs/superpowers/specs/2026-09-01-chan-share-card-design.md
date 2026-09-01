# 缠论 App 截图分享 + 下载二维码 — 设计

日期：2026-09-01
涉及：`ios/DeepAlphaChan/`（iOS App）、`frontend/app/app/`（中转页）

## 目标

分析结果页能一键生成一张自带品牌与下载二维码的分享图，让用户往微信/推特发结构分析
截图时，自然带上「这图哪来的」和「怎么下载」。

不做（YAGNI）：分享到指定平台的 SDK 接入、自定义配图模板选择、分享数据统计。
系统分享面板已覆盖全部去处；统计等有量了再说。

## 一、分享卡构图

单屏卡片（不是长图），自上而下：

```
┌────────────────────────────┐
│ TSLA · 日线       DeepAlpha │  标题栏：标的+周期 / 品牌
│ ┌────────────────────────┐ │
│ │  K线 + 分型/笔/线段     │ │  图表区：复用 ChanChartView
│ │  中枢/买卖点 + MACD     │ │  （禁用手势，窗口与用户所见一致）
│ └────────────────────────┘ │
│ 技术面偏强                  │  bias 标签（复用 SignalFormatting）
│ 股价站上前期整理区间…        │  narrative.headline，最多 2 行
│ 120根K线 · 8笔 · 3中枢      │  结构统计一行
│ ──────────────────────────  │
│ 算法生成，不构成投资建议 ▛▚▙ │  免责声明 + 二维码
│ 扫码下载 DeepAlpha 缠论  ▙▞▛ │
└────────────────────────────┘
```

设计宽度 375pt，`ImageRenderer` 以 `scale = 3` 输出 @3x 位图（1125pt 宽）。
高度由内容撑开，图表区高度沿用屏幕上的 `priceHeight 240 + macdHeight 78`。

**免责声明必须印在图上**：分享图会脱离 App 语境传播，这既是 App Store
3.1.1 / 5.2.5 的防线，也是发图人自己的风险隔离。

## 二、模块划分

新增目录 `ios/DeepAlphaChan/Share/`，三个文件各管一件事。工程用
`PBXFileSystemSynchronizedRootGroup`，新增 .swift 自动进编译，无需改 pbxproj。

| 文件 | 职责 | 对外接口 |
|---|---|---|
| `QRCode.swift` | URL → UIImage | `QRCode.image(for:size:) -> UIImage?` |
| `ShareCardView.swift` | 分享卡布局 | `ShareCardView(analysis:freq:window:)` |
| `ShareCardRenderer.swift` | 离屏渲染 + 分享面板 | `ShareCardRenderer.render(...) -> UIImage?`、`ShareSheet` |

- `QRCode`：CoreImage `CIQRCodeGenerator`，纠错级别 M，最近邻放大避免模糊；
  白底黑码（不跟随深色主题上色——扫码识别率优先于视觉统一）。
  同一 URL 的结果做静态缓存，避免每次分享重算。
- `ShareCardView`：纯展示，不持有状态；所有数据由参数传入，可 `#Preview` 目视。
- `ShareCardRenderer`：`@MainActor`，包装 `ImageRenderer`；`ShareSheet` 是
  `UIActivityViewController` 的 `UIViewControllerRepresentable` 封装。

## 三、图表窗口一致性

`ChanChartView` 的平移/缩放窗口目前是它自己的 `@State`
（`firstVisible` / `visibleCount`）。离屏渲染会新建实例，拿到的是默认的
「最新 60 根」，而不是用户当前拖到的那一段——分享出去的图和他看的不是同一段。

**改法**：把窗口显式化，而不是把状态搬走。

```swift
/// 图表可见窗口。分享渲染要复现用户当前看到的那一段，故把窗口显式化。
struct ChartWindow: Equatable {
    var firstVisible: Double
    var visibleCount: Double
}

struct ChanChartView: View {
    var initialWindow: ChartWindow? = nil          // 传入则用它，nil 走原默认
    var interactive: Bool = true                   // false 时不挂手势（分享渲染用）
    var onWindowChange: ((ChartWindow) -> Void)? = nil
}
```

- 内部 `@State` 保留，只在 `onAppear` 时若 `initialWindow != nil` 则采用它；
- 平移/缩放结束时回调 `onWindowChange`，由 `ResultDetailView` 存住最新窗口；
- `interactive == false` 时不安装手势、不画光标——分享图里不该有十字光标。

这样 `ChanChartView` 的调用方（结果页、全屏页、分享卡）都用同一份渲染逻辑，
窗口从哪来由调用方决定。646 行文件的隐藏状态因此变成显式契约。

## 四、入口与交互

`ResultDetailView` 导航栏右上角加分享按钮：

1. 点按 → `ShareCardRenderer.render()` 同步渲染（Canvas 绘制，几十毫秒）
2. 渲染期间按钮转 `ProgressView`，防连点
3. 渲染完 → `.sheet` 呈现 `ShareSheet`，同时带一段纯文本：
   `TSLA · 日线 | 技术面偏强 | DeepAlpha 缠论`
4. 渲染失败（`ImageRenderer.uiImage` 返回 nil）→ 弹 alert，不静默失败

不用 `ShareLink`：它要求 item 在视图构建时就存在，等于每次进结果页都白白预渲染一张图。

全屏图表页暂不加入口——横屏分享场景少，且横屏图配二维码排版另需一套。

## 五、二维码与中转页

二维码内容固定为 `https://deepalpha.club/app`，App 侧写死不变。

新增 `frontend/app/app/page.tsx`：

- 常量 `APP_STORE_ID`（字符串，初始为空）
- 为空 → 页面显示「即将上架」+ 邮箱联系方式
- 非空 → iOS UA 自动跳 `https://apps.apple.com/app/id<APP_STORE_ID>`，
  其余设备显示介绍 + App Store 徽章
- 跳转在客户端做（`useEffect` + UA 判断），避免边缘缓存把跳转固化

好处：二维码内容永不失效，拿到 App Store ID 后只改网页、不发 App 版本。

## 六、Info.plist

必须新增：

```xml
<key>NSPhotoLibraryAddUsageDescription</key>
<string>保存分析图到相册</string>
```

当前 Info.plist 没有这个键。用户在系统分享面板点「存储图像」时，
缺该键会直接崩溃——这是必修项，不是可选项。

## 七、验证

本工程**没有测试 target**（`ios/Tests` 属于 WordLens），因此不做单元测试。

### 已验证（自动化）

`DeepAlphaChanApp.swift` 里有一个 DEBUG-only 的自检 `ShareCardSelfTest`：带
`-shareCardSelfTest` 启动参数时用假数据渲染一张分享卡写进 Documents。它绕开了
登录与真实分析，把「离屏渲染管线是否可用」这个最大风险变成一条命令：

```bash
xcodebuild -project ios/DeepAlphaChan.xcodeproj -scheme DeepAlphaChan \
  -destination 'platform=iOS Simulator,name=iPhone 17' -derivedDataPath /tmp/chan-build build
xcrun simctl install "iPhone 17" /tmp/chan-build/Build/Products/Debug-iphonesimulator/DeepAlphaChan.app
xcrun simctl launch "iPhone 17" club.deepalpha.chan -shareCardSelfTest
cp "$(xcrun simctl get_app_container 'iPhone 17' club.deepalpha.chan data)/Documents/share-card.png" /tmp/
```

2026-09-01 实测结果：输出 1125×1534（375pt @3x），K 线 Canvas、结论、免责声明、
二维码全部正常渲染；用 `CIDetector` 从成品图里解码二维码，得到
`https://deepalpha.club/app`，与预期一致。

### 待验证（需要真机/登录，交给使用者）

模拟器上的登录无法自动化（模拟器吞掉 Cmd/Shift 修饰键，剪贴板粘贴进不去输入框），
以下三条需手动走一遍：

1. 平移图表后分享 → 确认图里是平移后的那一段、且无十字光标
2. 分享到微信正常显示
3. **点「存储图像」不崩溃**（验证 Info.plist 那个键确实生效）

## 八、边界情况

| 情况 | 处理 |
|---|---|
| `narrative` 为 nil | 退回 `analysis.summary`（与 AnalysisSection 一致） |
| `recommendation` 为 nil | 退回 `currentTrend` 的 trendLabel（同上） |
| headline 超长 | 最多 2 行，`lineLimit(2)` + 尾部截断 |
| `macd` 为 nil | 不画副图，卡片自然变矮 |
| K 线不足 10 根 | 沿用图表现有的 `max(10, ...)` 保护，不额外处理 |
| 渲染返回 nil | alert 提示「生成失败，请重试」 |
