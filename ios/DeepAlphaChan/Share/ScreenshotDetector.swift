import SwiftUI
import UIKit

/// 截图检测的底层 modifier：只负责「监听 + 防抖 + 自截 + 拼图」，自己不呈现任何 UI。
///
/// 与 `ShareOnScreenshot` 拆开是因为宿主页面可能已经有自己的 sheet（如结果详情页的
/// 分享按钮也要弹同一个预览）。同一视图层级挂两个 `.sheet` 在 SwiftUI 里会互相吞掉，
/// 所以把「谁来呈现」交还给宿主，这里只把拼好的图交出去。
///
/// 只在明确挂了这个 modifier 的页面生效，不做全 App 监听：在「我的」页截图会把
/// 邮箱地址拼进分享图。挂载页面见 spec —— 分析结果页、全屏图表页、学习页。
struct OnScreenshotCapture: ViewModifier {
    /// 是否响应截图。宿主的预览已经开着时传 false，避免「对着预览再截一张」的套娃。
    ///
    /// 做成参数而不是在这里自行判断：拆开后本 modifier 不再持有预览状态，
    /// 唯一知道「预览是否开着」的只有宿主。让宿主显式告知，比在这里猜要诚实，
    /// 也不会因为猜错而误吞掉一次真实的截图事件。
    let isEnabled: Bool
    /// 拼好的分享图（品牌头 + 截图 + 免责条）。
    let action: (UIImage) -> Void

    /// 上次响应截图的时间，用于防抖。
    @State private var lastFired = Date.distantPast

    func body(content: Content) -> some View {
        content
            .onReceive(NotificationCenter.default.publisher(
                for: UIApplication.userDidTakeScreenshotNotification)
            ) { _ in handleScreenshot() }
    }

    private func handleScreenshot() {
        guard isEnabled else { return }
        // 系统偶尔会连发通知，0.5 秒内的重复忽略
        guard Date().timeIntervalSince(lastFired) > 0.5 else { return }
        lastFired = Date()

        guard let shot = WindowCapture.capture(),
              let composed = ShareComposer.compose(screenshot: shot)
        else { return }  // 静默放弃，见 ShareComposer 注释

        action(composed)
    }
}

/// 截图触发分享的便捷 modifier：自带预览状态与 sheet。
///
/// 供那些本身没有别的 sheet 的页面（全屏图表页、学习页）一行接入。
/// 页面若已有自己的 sheet，请改用底层的 `onScreenshot(perform:)`。
struct ShareOnScreenshot: ViewModifier {
    /// 分享面板附带的文案。
    let shareText: String

    @State private var preview: SharePreviewItem?

    func body(content: Content) -> some View {
        content
            // 预览已经开着时不再响应：用户在预览里截图不该再弹一层
            .onScreenshot(isEnabled: preview == nil) { preview = SharePreviewItem(image: $0) }
            .sheet(item: $preview) { item in
                SharePreviewSheet(image: item.image, text: shareText)
            }
    }
}

/// `sheet(item:)` 要求 Identifiable，UIImage 不是，故包一层。
struct SharePreviewItem: Identifiable {
    let id = UUID()
    let image: UIImage
}

extension View {
    /// 监听本页面的截图，把拼好的分享图交给回调，由调用方决定怎么呈现。
    ///
    /// - Parameter isEnabled: 传 false 可临时停止响应（例如预览已经开着时）。
    func onScreenshot(isEnabled: Bool = true,
                      perform action: @escaping (UIImage) -> Void) -> some View {
        modifier(OnScreenshotCapture(isEnabled: isEnabled, action: action))
    }

    /// 在本页面启用「截图即分享」（含预览弹窗）。
    func shareOnScreenshot(text: String) -> some View {
        modifier(ShareOnScreenshot(shareText: text))
    }
}
