import SwiftUI

/// App 入口。持有全局的认证状态，根据是否登录切换根视图。
@main
struct DeepAlphaChanApp: App {
    @StateObject private var auth = AuthViewModel()
    @StateObject private var store = StoreManager()
    @StateObject private var usage = UsageTracker()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(auth)
                .environmentObject(store)
                .environmentObject(usage)
                .tint(Theme.accent)
                .preferredColorScheme(.dark)
        }
    }
}
