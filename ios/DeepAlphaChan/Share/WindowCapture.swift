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
