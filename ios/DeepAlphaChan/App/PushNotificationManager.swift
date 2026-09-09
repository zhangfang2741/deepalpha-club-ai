import SwiftUI
import UIKit
import UserNotifications

/// APNs 远程推送：权限、token 上报（带 App 语言）、点击路由到晨报对应市场。
///
/// token 上报时机：注册成功时、登录成功时、语言切换后重进 App 时
/// （后端按 locale 分组推送）。
@MainActor
final class PushNotificationManager: NSObject, ObservableObject, UNUserNotificationCenterDelegate {
    static let shared = PushNotificationManager()

    /// 最近一次拿到的 APNs token（hex），登录后上报。
    @Published private(set) var deviceToken: String?
    /// 上次成功上报时用的 locale，避免同语言重复上报。
    private var reportedLocale: String?
    private var reportedToken: String?
    private var reportedSession: String?
    @Published var pendingMarket: String?

    func prepare() {
        UNUserNotificationCenter.current().delegate = self
    }
    /// 权限申请与注册只做一次（登出再登录不重复弹窗）。
    private var activated = false

    func activate() {
        #if targetEnvironment(simulator)
        // 模拟器无法取得可用 APNs token，也不应让系统权限弹窗阻塞自动化录屏。
        return
        #else
        guard !activated else { return }
        activated = true
        UNUserNotificationCenter.current().delegate = self
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) {
            _, _ in
            // 无论授权与否都注册：被拒时拿不到 token 但不影响其余流程。
            DispatchQueue.main.async { UIApplication.shared.registerForRemoteNotifications() }
        }
        #endif
    }

    nonisolated func didRegister(deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        Task { @MainActor in
            self.deviceToken = token
            await self.reportIfPossible()
        }
    }

    nonisolated func didFailToRegister(error: Error) {
        // 模拟器无 APNs，静默即可（联调推送需真机）。
    }

    /// 登录成功 / 语言切换后调用：账号、设备或语言变化时重新绑定。
    func reportIfPossible() async {
        guard let token = deviceToken, let session = KeychainStore.loadToken() else { return }
        let locale = Localized.language() == .english ? "en" : "zh-Hans"
        guard locale != reportedLocale || token != reportedToken || session != reportedSession else { return }
        do {
            try await MorningReportService.registerDeviceToken(token, locale: locale)
            reportedLocale = locale
            reportedToken = token
            reportedSession = session
        } catch {
            // 上报失败不阻塞主流程，下次登录/切语言重试。
        }
    }

    // MARK: - 点击路由

    /// 冷启动/后台点击：系统回调后广播到 MainTabView 切换 Tab 与市场。
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let market = response.notification.request.content.userInfo["market"] as? String ?? "us"
        DispatchQueue.main.async {
            self.pendingMarket = StockMarket(rawValue: market) != nil ? market : "us"
        }
        completionHandler()
    }

    /// 前台收到也展示横幅。
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound])
    }
}
