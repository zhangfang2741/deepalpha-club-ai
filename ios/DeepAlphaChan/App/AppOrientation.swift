import SwiftUI
import UIKit

/// 全局屏幕方向锁。
///
/// 为什么需要它：全屏图表要能横过来看，这就必须在 Info.plist 里给 iPhone 放开
/// 横屏声明。但那个声明是**全 App 生效**的——不加约束的话，登录页、表单页
/// 也会跟着转，那些页面从没按横屏布局过，转过去就是一团糟。
///
/// 所以 Info.plist 放开，运行时收紧：默认只允许竖屏，只有全屏图表出现时才放开。
final class AppOrientation: ObservableObject {
    /// 当前允许的方向。AppDelegate 每次被系统询问时读它。
    @Published private(set) var mask: UIInterfaceOrientationMask = .portrait

    /// 允许横屏（进入全屏图表时调用）。
    func allowLandscape() {
        mask = .allButUpsideDown
        notifySystem()
    }

    /// 锁回竖屏，并把当前界面转回竖屏。
    ///
    /// 退出全屏时必须无条件调用，不能依赖任何成功回调——漏了的话用户从横屏
    /// 退出后整个 App 会卡在横屏，只能杀进程。
    func lockPortrait() {
        mask = .portrait
        notifySystem()
        requestGeometry(.portrait)
    }

    /// 告诉系统「支持的方向变了，重新问一次」。
    private func notifySystem() {
        UIViewController.attemptRotationToDeviceOrientation()
    }

    private func requestGeometry(_ orientations: UIInterfaceOrientationMask) {
        guard let scene = UIApplication.shared.connectedScenes
            .first(where: { $0 is UIWindowScene }) as? UIWindowScene else { return }
        scene.requestGeometryUpdate(.iOS(interfaceOrientations: orientations)) { error in
            // 请求被拒不致命：mask 已经改了，用户转一下手机系统就会重新询问。
            print("[AppOrientation] 方向请求失败: \(error.localizedDescription)")
        }
    }
}

/// 方向锁需要 UIKit 的 AppDelegate 回调，SwiftUI 生命周期本身没有这个钩子。
final class AppDelegate: NSObject, UIApplicationDelegate {
    /// 与 DeepAlphaChanApp 里的 @StateObject 是同一个实例，由 App 启动时注入。
    static var orientation: AppOrientation?

    func application(
        _ application: UIApplication,
        supportedInterfaceOrientationsFor window: UIWindow?
    ) -> UIInterfaceOrientationMask {
        AppDelegate.orientation?.mask ?? .portrait
    }
}
