import SwiftUI

/// 根视图：按登录状态切换登录页 / 主界面。
struct RootView: View {
    @EnvironmentObject var auth: AuthViewModel

    var body: some View {
        Group {
            if auth.isAuthenticated {
                ChanDashboardView()
            } else {
                LoginView()
            }
        }
        .animation(.easeInOut, value: auth.isAuthenticated)
    }
}
