import SwiftUI
import UIKit

/// 截图检测的底层 modifier：只负责「监听 + 自截 + 拼图」，自己不呈现任何 UI。
///
/// 与 `ShareOnScreenshot` 拆开是因为宿主页面可能已经有自己的 sheet（如结果详情页的
/// 分享按钮也要弹同一个预览）。同一视图层级挂两个 `.sheet` 在 SwiftUI 里会互相吞掉，
/// 所以把「谁来呈现」交还给宿主，这里只把拼好的图交出去。
///
/// 谁有资格响应由 `ScreenshotShareCoordinator` 全局仲裁（栈顶唯一 + 防抖）。
/// 本 modifier 不再自己猜可见性 —— 各自猜的旧方案挡不住子视图自带的 sheet：
/// 呈现方收不到 onDisappear，宿主在弹层之下仍然「可见」，两边同时弹 sheet
/// 抢同一个 presenter，输掉的那个状态永远停在非 nil，本页分享从此静默失效。
struct OnScreenshotCapture: ViewModifier {
    /// 是否响应截图。宿主的预览已经开着时传 false，避免「对着预览再截一张」的套娃。
    ///
    /// 做成参数而不是在这里自行判断：拆开后本 modifier 不再持有预览状态，
    /// 唯一知道「预览是否开着」的只有宿主。这是宿主语义的门，与协调器的
    /// 呈现仲裁是两层不同的门，前者管「本页想不想」，后者管「轮不轮得到」。
    let isEnabled: Bool
    /// 拼好的分享图（品牌头 + 截图 + 免责条）。
    let action: (UIImage) -> Void

    /// 本挂载点在协调器栈里的身份。
    ///
    /// 必须是 @State 而不是 let：宿主 body 每次重算都会重建本 modifier 实例，
    /// let 的话 id 跟着变，事件到来时与栈里登记的对不上号，截一次之后就永远失效。
    @State private var coordinatorID = UUID()

    func body(content: Content) -> some View {
        content
            .onAppear { ScreenshotShareCoordinator.shared.push(coordinatorID) }
            .onDisappear { ScreenshotShareCoordinator.shared.remove(coordinatorID) }
            .onReceive(NotificationCenter.default.publisher(
                for: UIApplication.userDidTakeScreenshotNotification)
            ) { _ in handleScreenshot() }
    }

    private func handleScreenshot() {
        guard isEnabled else { return }
        guard ScreenshotShareCoordinator.shared.shouldHandle(coordinatorID) else { return }

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

/// 显式声明「本页面不参与截图分享」。
///
/// 挂上后页面出现时同样登记进协调器栈：事件到栈顶是它就等于被吞掉 ——
/// 底下所有挂载点的 `shouldHandle` 都因「非栈顶」被拒。它自己不监听通知、
/// 也不消耗防抖窗口：若非栈顶时误动 lastFired，反而可能吞掉真正的响应者。
struct SuppressScreenshotShare: ViewModifier {
    /// 见 `OnScreenshotCapture.coordinatorID`：必须 @State，不能 let。
    @State private var coordinatorID = UUID()

    func body(content: Content) -> some View {
        content
            .onAppear { ScreenshotShareCoordinator.shared.push(coordinatorID) }
            .onDisappear { ScreenshotShareCoordinator.shared.remove(coordinatorID) }
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

    /// 抑制本页面的截图分享：隐私页（登录/注册/找回密码/付费墙/我的）与
    /// 结果页、全屏图表页上的临时弹层挂这个，事件到此为止，不漏给底下的页面。
    /// 隐私边界由此从「依赖别人的 onDisappear」变成每个页面自己的显式声明。
    func suppressScreenshotShare() -> some View {
        modifier(SuppressScreenshotShare())
    }
}
