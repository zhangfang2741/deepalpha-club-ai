# 截图即分享 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户在 App 内截图后，自动生成「品牌头 + 原界面截图 + 免责条」的分享图并弹出预览，让用户看清再发。

**Architecture:** iOS 不提供读取用户所截图片的 API，`userDidTakeScreenshotNotification` 只告知「刚发生了截图」。因此由 App 收到通知时对当前 window 自截一张（内容一致，仅少了系统状态栏），再拼上品牌头与免责条。几何计算抽成不依赖 UIKit 的 `ShareLayout` 以便自动化测试，绘制交给 `ShareComposer`，两者只经 `CGRect`/`UIImage` 通信。

**Tech Stack:** SwiftUI、UIKit（`UIGraphicsImageRenderer`、`UIActivityViewController`）、CoreImage（既有 `QRCode`）。测试沿用仓库既有的 `swiftc` 编译真实源文件 + 断言脚本模式，不引入 XCTest target。

**Spec:** `docs/superpowers/specs/2026-09-02-screenshot-share-design.md`

---

## 背景：这个仓库的测试怎么跑

本工程**没有 XCTest target**。工程用 `PBXFileSystemSynchronizedRootGroup` 组织，
手工往 `project.pbxproj` 里加 target 风险大于收益。既有做法见
`ios/Tests/run-dictation-judge-tests.sh`：用 `swiftc` 编译**真实源文件** + 一个
写满断言的 `main.swift`，编译产物直接跑，非零退出码即失败。

该模式在 macOS 命令行下编译，**UIKit / SwiftUI 不可用**。所以只有纯几何的
`ShareLayout` 能进自动化测试；`ShareComposer`、`WindowCapture`、各视图靠 SwiftUI
Preview 与真机验证。Task 1 建立测试脚手架，Task 2 起才有东西可测。

---

## Task 1: ShareLayout 几何层（纯函数，可测）

**Files:**
- Create: `ios/DeepAlphaChan/Share/ShareLayout.swift`
- Create: `ios/Tests/ShareLayoutTests.swift`
- Create: `ios/Tests/run-share-layout-tests.sh`

- [ ] **Step 1: 写测试脚本（先建可运行的失败环境）**

创建 `ios/Tests/run-share-layout-tests.sh`：

```bash
#!/bin/bash
# 分享图几何计算的回归测试。
#
# 同 run-dictation-judge-tests.sh：工程没有 XCTest target，直接用 swiftc 编译
# **真实源文件** + 断言脚本。ShareLayout 刻意不依赖 UIKit，就是为了能在这里跑。
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT=$(mktemp -d)/sharelayouttest
swiftc -O \
  "$ROOT/ios/DeepAlphaChan/Share/ShareLayout.swift" \
  "$ROOT/ios/Tests/ShareLayoutTests.swift" \
  -o "$OUT"
"$OUT"
```

然后 `chmod +x ios/Tests/run-share-layout-tests.sh`

- [ ] **Step 2: 写失败的测试**

创建 `ios/Tests/ShareLayoutTests.swift`。

注意 Swift 的一条硬性规则：**多文件一起用 `swiftc` 编译时，含顶层可执行语句的文件必须命名为 `main.swift`**。
而 `ios/Tests/main.swift` 已被 `run-dictation-judge-tests.sh` 占用，同目录不能重名。
因此断言代码要用 `@main struct` 包一层 —— `@main` 类型对文件名没有限制。

```swift
import CoreGraphics
import Foundation

// Swift 规则：多文件一起用 swiftc 编译时，含顶层语句的文件必须叫 main.swift，
// 而 ios/Tests/main.swift 这个文件名已被 run-dictation-judge-tests.sh 占用，
// 不能重名冲突。用 @main 包一层，就能把断言代码放进任意文件名里。
@main
struct ShareLayoutTestsMain {
    static var failures = 0

    static func expect(_ actual: CGFloat, _ expected: CGFloat, _ note: String) {
        let ok = abs(actual - expected) < 0.01
        if !ok { failures += 1 }
        print("\(ok ? "PASS" : "FAIL")  \(note)  实际 \(actual) 期望 \(expected)")
    }

    static func expectTrue(_ cond: Bool, _ note: String) {
        if !cond { failures += 1 }
        print("\(cond ? "PASS" : "FAIL")  \(note)")
    }

    static func main() {
        print("=== 竖屏截图（iPhone 15 Pro，390x844）===")
        let portrait = ShareLayout.compute(screenshotSize: CGSize(width: 390, height: 844))
        expect(portrait.totalSize.width, 390, "总宽 = 截图宽")
        expect(portrait.totalSize.height, 844 + ShareLayout.bannerHeight + ShareLayout.disclaimerHeight,
               "总高 = 截图高 + 品牌头 + 免责条")
        expect(portrait.bannerRect.origin.y, 0, "品牌头在最上")
        expect(portrait.screenshotRect.origin.y, ShareLayout.bannerHeight, "截图紧接品牌头下方")
        expect(portrait.disclaimerRect.origin.y, ShareLayout.bannerHeight + 844, "免责条在最下")
        expect(portrait.bannerRect.width, 390, "品牌头宽度跟随截图，不是写死 375")

        print("\n=== 横屏截图（全屏图表，844x390）===")
        let landscape = ShareLayout.compute(screenshotSize: CGSize(width: 844, height: 390))
        expect(landscape.totalSize.width, 844, "横图总宽 = 截图宽")
        expect(landscape.bannerRect.width, 844, "品牌头随横图变宽")
        expect(landscape.totalSize.height, 390 + ShareLayout.bannerHeight + ShareLayout.disclaimerHeight,
               "横图总高")

        print("\n=== 三块不重叠、无负高度 ===")
        for (name, l) in [("竖图", portrait), ("横图", landscape)] {
            expectTrue(l.bannerRect.maxY <= l.screenshotRect.minY + 0.01, "\(name)：品牌头不压住截图")
            expectTrue(l.screenshotRect.maxY <= l.disclaimerRect.minY + 0.01, "\(name)：截图不压住免责条")
            expectTrue(l.bannerRect.height > 0 && l.screenshotRect.height > 0 && l.disclaimerRect.height > 0,
                       "\(name)：三块高度均为正")
            expectTrue(l.disclaimerRect.maxY <= l.totalSize.height + 0.01, "\(name)：免责条不超出画布")
        }

        print("\n=== 极端宽高比 ===")
        let narrow = ShareLayout.compute(screenshotSize: CGSize(width: 100, height: 2000))
        expect(narrow.totalSize.width, 100, "极窄图总宽")
        expectTrue(narrow.bannerRect.height > 0, "极窄图品牌头高度仍为正")
        let wide = ShareLayout.compute(screenshotSize: CGSize(width: 3000, height: 80))
        expect(wide.totalSize.width, 3000, "极宽图总宽")
        expectTrue(wide.screenshotRect.height > 0, "极宽图截图区高度仍为正")

        print("\n\(failures == 0 ? "全部通过" : "\(failures) 项失败")")
        exit(failures == 0 ? 0 : 1)
    }
}
```

- [ ] **Step 3: 运行测试，确认失败**

Run: `./ios/Tests/run-share-layout-tests.sh`
Expected: 编译失败，`error: cannot find 'ShareLayout' in scope`

- [ ] **Step 4: 写最小实现**

创建 `ios/DeepAlphaChan/Share/ShareLayout.swift`：

```swift
import CoreGraphics

/// 分享图的几何计算。
///
/// 刻意只依赖 CoreGraphics，不碰 UIKit/SwiftUI：本工程没有 XCTest target，
/// 测试靠 swiftc 在 macOS 命令行下编译真实源文件（见 run-share-layout-tests.sh），
/// 那里 UIKit 不可用。把几何单独拆出来，这部分才测得了。
enum ShareLayout {
    /// 品牌头高度（App 图标 + 名称 + slogan + 二维码）。
    static let bannerHeight: CGFloat = 88
    /// 免责条高度。一行小字，够用即可。
    static let disclaimerHeight: CGFloat = 24

    /// 一张分享图里三块内容的位置。
    struct Result {
        let totalSize: CGSize
        let bannerRect: CGRect
        let screenshotRect: CGRect
        let disclaimerRect: CGRect
    }

    /// 按截图尺寸算出整图布局。
    ///
    /// 宽度完全跟随截图，不写死 375：全屏图表页是横屏，截出来是横图。
    static func compute(screenshotSize: CGSize) -> Result {
        let w = screenshotSize.width
        let h = screenshotSize.height

        let banner = CGRect(x: 0, y: 0, width: w, height: bannerHeight)
        let shot = CGRect(x: 0, y: bannerHeight, width: w, height: h)
        let disclaimer = CGRect(x: 0, y: bannerHeight + h, width: w, height: disclaimerHeight)

        return Result(
            totalSize: CGSize(width: w, height: bannerHeight + h + disclaimerHeight),
            bannerRect: banner,
            screenshotRect: shot,
            disclaimerRect: disclaimer
        )
    }
}
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `./ios/Tests/run-share-layout-tests.sh`
Expected: 全部 PASS，最后一行「全部通过」，退出码 0

- [ ] **Step 6: 提交**

```bash
git add ios/DeepAlphaChan/Share/ShareLayout.swift ios/Tests/ShareLayoutTests.swift ios/Tests/run-share-layout-tests.sh
git commit -m "feat(ios/chan): 分享图几何计算层 ShareLayout + 回归测试"
```

---

## Task 2: WindowCapture 自截当前窗口

**Files:**
- Create: `ios/DeepAlphaChan/Share/WindowCapture.swift`

无自动化测试：依赖 UIKit 的 window 层级，命令行编译不了，且需要真实运行的 App 才有 window。真机验证放在 Task 8。

- [ ] **Step 1: 写实现**

创建 `ios/DeepAlphaChan/Share/WindowCapture.swift`：

```swift
import UIKit

/// 把当前前台窗口截成图片。
///
/// iOS 不提供读取用户所截图片的 API —— `userDidTakeScreenshotNotification` 只告知
/// 「刚发生了截图」，不含图像。所以收到通知后由我们自己再截一张，内容与用户所截一致，
/// 唯一差别是没有状态栏（状态栏属于系统独立 window，App 截不到）。
@MainActor
enum WindowCapture {
    /// 截当前前台 window。失败返回 nil，调用方静默放弃。
    static func capture() -> UIImage? {
        guard let window = foregroundWindow() else { return nil }

        let renderer = UIGraphicsImageRenderer(bounds: window.bounds)
        let image = renderer.image { ctx in
            // drawHierarchy 取的是已渲染内容，比 layer.render 更贴近用户看到的画面。
            // afterScreenUpdates: false —— 通知回调里不该再触发一次重排。
            if !window.drawHierarchy(in: window.bounds, afterScreenUpdates: false) {
                // 某些图层（Metal、部分系统模糊）drawHierarchy 会返回 false 且画不出来，
                // 降级走 layer 渲染。两者都不行就得到一张空图，由调用方判空。
                window.layer.render(in: ctx.cgContext)
            }
        }
        return image
    }

    private static func foregroundWindow() -> UIWindow? {
        UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .first { $0.activationState == .foregroundActive }?
            .keyWindow
    }
}
```

- [ ] **Step 2: 确认能编译**

Run: `./ios/Tests/build-check.sh`
Expected: 末行 `** BUILD SUCCEEDED **`，退出码 0

- [ ] **Step 3: 提交**

```bash
git add ios/DeepAlphaChan/Share/WindowCapture.swift
git commit -m "feat(ios/chan): 自截当前窗口 WindowCapture"
```

---

## Task 3: ShareBanner 品牌头与免责条

**Files:**
- Create: `ios/DeepAlphaChan/Share/ShareBanner.swift`

- [ ] **Step 1: 写实现**

创建 `ios/DeepAlphaChan/Share/ShareBanner.swift`：

```swift
import SwiftUI

/// 分享图顶部的品牌头：图标 + 名称 + slogan + 下载二维码。
///
/// 高度固定为 `ShareLayout.bannerHeight`，宽度由外部按截图宽度给定 ——
/// 全屏图表页是横屏，截出来是横图，写死宽度会错位。
struct ShareBanner: View {
    let width: CGFloat

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            // 用 SF Symbol 而不是 App 图标：Assets 里只有 AppIcon.appiconset，
            // 那是 App 图标专用的，不能当普通 Image 引用。
            Image(systemName: "chart.xyaxis.line")
                .font(.system(size: 22, weight: .semibold))
                .foregroundColor(Theme.accent)
                .frame(width: 40, height: 40)
                .background(Theme.accent.opacity(0.14))
                .clipShape(RoundedRectangle(cornerRadius: 9))

            VStack(alignment: .leading, spacing: 3) {
                Text("DeepAlpha \(L("缠论"))")
                    .font(.system(size: 17, weight: .bold))
                    .foregroundColor(Theme.textPrimary)
                // 只陈述功能。分享图会脱离 App 语境传播，不能出现「先机」「收益」
                // 这类暗示性措辞。
                Text(L("缠论结构 自动标注"))
                    .font(.system(size: 12))
                    .foregroundColor(Theme.textSecondary)
            }

            Spacer(minLength: 0)

            qrCode
        }
        .padding(.horizontal, 16)
        .frame(width: width, height: ShareLayout.bannerHeight)
        .background(Theme.surface)
    }

    @ViewBuilder
    private var qrCode: some View {
        if let qr = QRCode.image(for: AppConfig.downloadPageURL, side: 64) {
            Image(uiImage: qr)
                .resizable()
                .frame(width: 64, height: 64)
                // 白色内边距是二维码的「静默区」，紧贴深色底会明显掉识别率
                .padding(3)
                .background(Color.white)
                .clipShape(RoundedRectangle(cornerRadius: 4))
        }
    }
}

/// 分享图底部的免责条。
///
/// 这行字不可省。分享图会脱离 App 语境传播，被当成荐股截图转发时，它是唯一还跟着图走的
/// 风险说明。用户截屏时未必滚动到了结果页底部那行 compactDisclaimer，所以由品牌层无条件补上。
struct ShareDisclaimer: View {
    let width: CGFloat

    var body: some View {
        Text(L("算法自动生成，仅供技术研究，不构成投资建议。"))
            .font(.system(size: 10))
            .foregroundColor(Theme.textSecondary)
            .frame(width: width, height: ShareLayout.disclaimerHeight)
            .background(Theme.surface)
    }
}

#if DEBUG
#Preview("品牌头与免责条") {
    VStack(spacing: 0) {
        ShareBanner(width: 390)
        Rectangle().fill(Theme.background).frame(width: 390, height: 200)
            .overlay(Text("（此处为用户界面截图）").foregroundColor(Theme.textSecondary))
        ShareDisclaimer(width: 390)
    }
    .preferredColorScheme(.dark)
}
#endif
```

- [ ] **Step 2: 确认能编译**

Run: `./ios/Tests/build-check.sh`
Expected: 末行 `** BUILD SUCCEEDED **`，退出码 0

（`#Preview` 的目视确认需要 Xcode GUI，无法在命令行完成，归入 Task 8 真机验证。）

- [ ] **Step 3: 提交**

```bash
git add ios/DeepAlphaChan/Share/ShareBanner.swift
git commit -m "feat(ios/chan): 分享图品牌头与免责条"
```

---

## Task 4: ShareComposer 拼图

**Files:**
- Create: `ios/DeepAlphaChan/Share/ShareComposer.swift`

- [ ] **Step 1: 写实现**

创建 `ios/DeepAlphaChan/Share/ShareComposer.swift`：

```swift
import SwiftUI
import UIKit

/// 把截图拼成最终分享图：品牌头 + 原截图 + 免责条。
///
/// 位置全部由 `ShareLayout` 算好，这里只负责画。分工是为了让几何部分能在
/// 没有 UIKit 的命令行测试里跑（见 ShareLayout.swift 注释）。
@MainActor
enum ShareComposer {
    /// 拼图。
    ///
    /// - Parameter screenshot: `WindowCapture.capture()` 的产物。
    /// - Returns: 失败返回 nil，调用方静默放弃 —— 用户只是截了个图，
    ///   为一个他没主动发起的功能弹错误框很打扰。
    static func compose(screenshot: UIImage) -> UIImage? {
        let layout = ShareLayout.compute(screenshotSize: screenshot.size)

        guard let banner = render(ShareBanner(width: layout.bannerRect.width),
                                  size: layout.bannerRect.size),
              let disclaimer = render(ShareDisclaimer(width: layout.disclaimerRect.width),
                                      size: layout.disclaimerRect.size)
        else { return nil }

        // 按截图自身的 scale 输出，保证拼接后不糊
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = screenshot.scale
        let renderer = UIGraphicsImageRenderer(size: layout.totalSize, format: format)

        return renderer.image { _ in
            banner.draw(in: layout.bannerRect)
            screenshot.draw(in: layout.screenshotRect)
            disclaimer.draw(in: layout.disclaimerRect)
        }
    }

    /// 把 SwiftUI 视图离屏渲染成位图。
    private static func render<V: View>(_ view: V, size: CGSize) -> UIImage? {
        let renderer = ImageRenderer(content: view.frame(width: size.width, height: size.height))
        // 与截图同倍率，避免品牌头比截图糊
        renderer.scale = UIScreen.main.scale
        return renderer.uiImage
    }
}
```

- [ ] **Step 2: 确认能编译**

Run: `./ios/Tests/build-check.sh`
Expected: 末行 `** BUILD SUCCEEDED **`，退出码 0

- [ ] **Step 3: 提交**

```bash
git add ios/DeepAlphaChan/Share/ShareComposer.swift
git commit -m "feat(ios/chan): 分享图拼接 ShareComposer"
```

---

## Task 5: SharePreviewSheet 预览弹窗

**Files:**
- Create: `ios/DeepAlphaChan/Share/SharePreviewSheet.swift`

- [ ] **Step 1: 写实现**

创建 `ios/DeepAlphaChan/Share/SharePreviewSheet.swift`：

```swift
import SwiftUI
import UIKit

/// 分享前的预览弹窗。
///
/// 存在的理由：原来点分享直接弹系统面板，用户没见过图就发出去了。系统面板顶部那个
/// 缩略图只有几十像素，等于盲发。
struct SharePreviewSheet: View {
    let image: UIImage
    /// 分享面板附带的一句话文案。
    let text: String

    @Environment(\.dismiss) private var dismiss
    @State private var showShareSheet = false
    @State private var savedHint: String?

    var body: some View {
        VStack(spacing: 16) {
            ScrollView {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                    .padding(.horizontal, 20)
                    .padding(.top, 16)
            }

            if let savedHint {
                Text(savedHint)
                    .font(.footnote)
                    .foregroundColor(Theme.textSecondary)
            }

            HStack(spacing: 12) {
                Button(action: saveToAlbum) {
                    Text(L("保存到相册"))
                        .font(.system(size: 16, weight: .medium))
                        .frame(maxWidth: .infinity, minHeight: 48)
                        .background(Theme.surfaceAlt)
                        .foregroundColor(Theme.textPrimary)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                }

                Button { showShareSheet = true } label: {
                    Text(L("分享"))
                        .font(.system(size: 16, weight: .semibold))
                        .frame(maxWidth: .infinity, minHeight: 48)
                        .background(Theme.accent)
                        .foregroundColor(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                }
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 8)
        }
        .background(Theme.background)
        .sheet(isPresented: $showShareSheet) {
            ShareSheet(items: [image, text])
        }
    }

    private func saveToAlbum() {
        UIImageWriteToSavedPhotosAlbum(image, nil, nil, nil)
        savedHint = L("已保存到相册")
    }
}
```

- [ ] **Step 2: 确认 ShareSheet 仍存在**

Run: `grep -n "struct ShareSheet" ios/DeepAlphaChan/Share/ShareCardRenderer.swift`
Expected: 有输出（Task 7 才会把它挪走，此刻仍在原处）

- [ ] **Step 3: 确认能编译**

Run: `./ios/Tests/build-check.sh`
Expected: 末行 `** BUILD SUCCEEDED **`，退出码 0

- [ ] **Step 4: 提交**

```bash
git add ios/DeepAlphaChan/Share/SharePreviewSheet.swift
git commit -m "feat(ios/chan): 分享前预览弹窗"
```

---

## Task 6: ScreenshotDetector 截图监听

**Files:**
- Create: `ios/DeepAlphaChan/Share/ScreenshotDetector.swift`

- [ ] **Step 1: 写实现**

创建 `ios/DeepAlphaChan/Share/ScreenshotDetector.swift`：

```swift
import SwiftUI
import UIKit

/// 截图触发分享的 modifier。
///
/// 只在明确挂了这个 modifier 的页面生效，不做全 App 监听：在「我的」页截图会把
/// 邮箱地址拼进分享图。挂载页面见 spec —— 分析结果页、全屏图表页、学习页。
struct ShareOnScreenshot: ViewModifier {
    /// 分享面板附带的文案。
    let shareText: String

    @State private var preview: SharePreviewItem?
    /// 上次响应截图的时间，用于防抖。
    @State private var lastFired = Date.distantPast

    func body(content: Content) -> some View {
        content
            .onReceive(NotificationCenter.default.publisher(
                for: UIApplication.userDidTakeScreenshotNotification)
            ) { _ in handleScreenshot() }
            .sheet(item: $preview) { item in
                SharePreviewSheet(image: item.image, text: shareText)
            }
    }

    private func handleScreenshot() {
        // 预览已经开着时不再套娃：用户在预览里截图不该再弹一层
        guard preview == nil else { return }
        // 系统偶尔会连发通知，0.5 秒内的重复忽略
        guard Date().timeIntervalSince(lastFired) > 0.5 else { return }
        lastFired = Date()

        guard let shot = WindowCapture.capture(),
              let composed = ShareComposer.compose(screenshot: shot)
        else { return }  // 静默放弃，见 ShareComposer 注释

        preview = SharePreviewItem(image: composed)
    }
}

/// `sheet(item:)` 要求 Identifiable，UIImage 不是，故包一层。
struct SharePreviewItem: Identifiable {
    let id = UUID()
    let image: UIImage
}

extension View {
    /// 在本页面启用「截图即分享」。
    func shareOnScreenshot(text: String) -> some View {
        modifier(ShareOnScreenshot(shareText: text))
    }
}
```

- [ ] **Step 2: 确认能编译**

Run: `./ios/Tests/build-check.sh`
Expected: 末行 `** BUILD SUCCEEDED **`，退出码 0

- [ ] **Step 3: 提交**

```bash
git add ios/DeepAlphaChan/Share/ScreenshotDetector.swift
git commit -m "feat(ios/chan): 截图监听与防抖"
```

---

## Task 7: 接入页面 + 删除旧精排卡

**Files:**
- Modify: `ios/DeepAlphaChan/Views/Analysis/ResultDetailView.swift`
- Modify: `ios/DeepAlphaChan/Views/Analysis/ChartFullscreenView.swift`
- Modify: `ios/DeepAlphaChan/Views/Learn/LearnTabView.swift`
- Modify: `ios/DeepAlphaChan/Share/ShareCardRenderer.swift`
- Delete: `ios/DeepAlphaChan/Share/ShareCardView.swift`

- [ ] **Step 1: 瘦身 ShareCardRenderer**

把 `ios/DeepAlphaChan/Share/ShareCardRenderer.swift` **整个文件**替换为：

```swift
import SwiftUI
import UIKit

/// 分享文案。图片本身由 ShareComposer 生成（截图 + 品牌头），这里只管附带的一句话。
@MainActor
enum ShareCardRenderer {
    /// 分享面板附带的一句话文案（微信等会把它作为消息文字）。
    static func shareText(analysis: ChanAnalysis, vm: ChanViewModel) -> String {
        let freq = vm.freq == "weekly" ? L("周线") : L("日线")
        let bias: String
        if let rec = analysis.recommendation {
            bias = SignalFormatting.biasLabel(rec.bias)
        } else {
            bias = SignalFormatting.trendLabel(analysis.currentTrend)
        }
        return "\(analysis.symbol.uppercased()) · \(freq) | \(bias) | DeepAlpha \(L("缠论"))"
    }
}

/// 系统分享面板。
struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
```

- [ ] **Step 2: 删除旧的精排卡**

```bash
git rm ios/DeepAlphaChan/Share/ShareCardView.swift
```

- [ ] **Step 3: 改造 ResultDetailView 的分享路径**

在 `ios/DeepAlphaChan/Views/Analysis/ResultDetailView.swift` 中：

把 `share()` 方法（约 86-99 行）替换为：

```swift
    /// 点按才渲染：进页面就预渲染的话，绝大多数不分享的用户白付这份开销。
    private func share() {
        isRendering = true
        // 让按钮先切到 loading 再开渲染，否则同步渲染会把这一帧吃掉，看着像没反应
        DispatchQueue.main.async {
            defer { isRendering = false }
            guard let shot = WindowCapture.capture(),
                  let composed = ShareComposer.compose(screenshot: shot) else {
                showShareError = true
                return
            }
            shareItem = ShareItem(image: composed,
                                  text: ShareCardRenderer.shareText(analysis: analysis, vm: vm))
        }
    }
```

在该视图 body 的最外层修饰符链上追加（与既有 `.alert(...)` 同级）：

```swift
        .shareOnScreenshot(text: ShareCardRenderer.shareText(analysis: analysis, vm: vm))
```

主动点按钮走 `shareItem` 现有的 sheet；截图走 modifier 自己的 sheet。两条路都拿同一张拼好的图。

- [ ] **Step 4: 全屏页移除图层开关**

在 `ios/DeepAlphaChan/Views/Analysis/ChartFullscreenView.swift` 中：

删掉这两行（第 27-28 行）：

```swift
                LayerToggles(vm: vm)
                    .padding(.horizontal, 12)
```

把 `chromeHeight`（第 14-15 行）改为：

```swift
    /// 顶栏 + 图例 + 上下留白占掉的高度，剩下的全给图表。
    /// 图层开关已移除 —— 全屏的用途是尽可能大地看图，开关占的 42pt 还给图表。
    /// 图层状态沿用进入全屏前在竖屏结果页的设置。
    private let chromeHeight: CGFloat = 90
```

在 `.background(Theme.background.ignoresSafeArea())` 之后追加：

```swift
        .shareOnScreenshot(text: "\(vm.symbol.uppercased()) · \(vm.freq == "weekly" ? L("周线") : L("日线")) | DeepAlpha \(L("缠论"))")
```

- [ ] **Step 5: 学习页接入**

`ios/DeepAlphaChan/Views/Learn/LearnTabView.swift` 第 7-19 行现为：

```swift
    var body: some View {
        NavigationStack {
            Group {
                if articles.isEmpty {
                    emptyState
                } else {
                    list
                }
            }
            .background(Theme.background)
            .navigationTitle(L("缠论入门"))
        }
    }
```

改为（modifier 挂在 `NavigationStack` **之后**，不是里面 —— 挂在里面弹窗会被导航层裁切）：

```swift
    var body: some View {
        NavigationStack {
            Group {
                if articles.isEmpty {
                    emptyState
                } else {
                    list
                }
            }
            .background(Theme.background)
            .navigationTitle(L("缠论入门"))
        }
        .shareOnScreenshot(text: "DeepAlpha \(L("缠论")) · \(L("缠论入门"))")
    }
```

- [ ] **Step 6: 确认没有残留引用**

Run: `grep -rn "ShareCardView\|ShareCardRenderer.render" ios/DeepAlphaChan/`
Expected: 无输出

- [ ] **Step 7: 确认几何测试仍通过**

Run: `./ios/Tests/run-share-layout-tests.sh`
Expected: 全部 PASS，退出码 0

- [ ] **Step 8: 确认能编译**

Run: `./ios/Tests/build-check.sh`
Expected: 末行 `** BUILD SUCCEEDED **`，退出码 0

- [ ] **Step 9: 提交**

```bash
git add -A ios/DeepAlphaChan/
git commit -m "feat(ios/chan): 截图即分享接入三个页面，全屏页移除图层开关"
```

---

## Task 8: 真机验证

自动化覆盖不到的部分。需要真机（模拟器可用 `Cmd+S` 模拟截图）。

- [ ] **Step 1: 结果页截图**

在分析结果页按电源+音量截图。
Expected: 底部弹出预览，图为「品牌头 + 结果页原样 + 免责条」，二维码清晰

- [ ] **Step 2: 扫码验证**

用另一台手机扫预览图里的二维码。
Expected: 打开 `https://deepalpha.club/app`，iOS 设备自动跳转 App Store

- [ ] **Step 3: 分享到微信**

预览页点「分享」→ 微信。
Expected: 图完整、未被裁切，附带文案形如 `AAPL · 日线 | 看多 | DeepAlpha 缠论`

- [ ] **Step 4: 保存到相册**

预览页点「保存到相册」。
Expected: 首次弹系统授权，允许后提示「已保存到相册」，相册中可见

- [ ] **Step 5: 横屏全屏页截图**

进全屏图表页（横屏）后截图。
Expected: 横向构图正常，品牌头横向铺满，图表比竖屏时明显更高

- [ ] **Step 6: 隐私边界**

在「我的」页、登录页、付费墙分别截图。
Expected: **不**弹出预览

- [ ] **Step 7: 防抖**

在结果页连续快速截图两次。
Expected: 只弹一次预览

- [ ] **Step 8: 预览中截图**

预览弹窗打开时再截图一次。
Expected: 不弹第二层

- [ ] **Step 9: 记录结果**

把验证结果补进 spec 的「验证」章节，通过的打勾，未通过的记录现象。

```bash
git add docs/superpowers/specs/2026-09-02-screenshot-share-design.md
git commit -m "docs(ios/chan): 补充截图分享真机验证结果"
```

---

## 完成标准

- [ ] `./ios/Tests/run-share-layout-tests.sh` 退出码 0
- [ ] Xcode Build Succeeded，无新增警告
- [ ] Task 8 全部真机项通过
- [ ] `grep -rn "ShareCardView" ios/` 无输出
