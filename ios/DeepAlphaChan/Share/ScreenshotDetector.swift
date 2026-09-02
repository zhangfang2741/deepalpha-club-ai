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
///
/// 不复用 `ShareCardRenderer.swift` 里已有的 `ShareItem`：那个是给分享卡渲染流程用的，
/// 名字撞车但语义不同，且下个任务会改动它，混用会互相牵连。
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
