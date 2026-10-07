import SwiftUI

/// 根视图：按登录状态切换登录页 / 主界面。
struct RootView: View {
    @EnvironmentObject var auth: AuthViewModel

    var body: some View {
        Group {
            if auth.isAuthenticated {
                MainTabView()
                    // 登录后才申请推送权限（符合审核惯例）；重进 App 时覆盖语言切换后的重报。
                    .task {
                        // 晨报隐藏期间（MainTabView）不申请推送权限，并注销老版本注册过的推送
                        guard AppConfig.morningReportEnabled else {
                            PushNotificationManager.shared.deactivate()
                            return
                        }
                        #if DEBUG && targetEnvironment(simulator)
                        // 运营录屏不依赖通知，避免首次权限弹窗遮挡自动播放。
                        guard !ProcessInfo.processInfo.arguments.contains("-marketingPlayback") else { return }
                        #endif
                        PushNotificationManager.shared.activate()
                        await PushNotificationManager.shared.reportIfPossible()
                    }
            } else {
                LoginView()
            }
        }
        .animation(.easeInOut, value: auth.isAuthenticated)
    }
}
