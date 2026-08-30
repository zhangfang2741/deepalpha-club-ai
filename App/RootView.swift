import SwiftUI
import DeepAlphaCore

/// 登录态路由：有 token 进主页，否则登录页。观察 deskVM 的 401 一并处理。
struct RootView: View {
    @Environment(AppState.self) private var appState
    @Environment(TradingDeskViewModel.self) private var deskVM

    var body: some View {
        ZStack {
            if appState.isLoggedIn {
                MainTabView()
            } else {
                LoginView()
            }
        }
        .animation(.easeInOut(duration: 0.2), value: appState.isLoggedIn)
        .onChange(of: deskVM.lastAuthError) { _, err in
            if err == .unauthorized { appState.handleUnauthorized() }
        }
    }
}

/// 主页：交易台 / 历史 两个 tab（自用 App 无需更多）。
struct MainTabView: View {
    var body: some View {
        TabView {
            TradingDeskView()
                .tabItem { Label("交易台", systemImage: "chart.line.uptrend.xyaxis") }
            HistoryListView()
                .tabItem { Label("历史", systemImage: "clock.arrow.circlepath") }
        }
    }
}
