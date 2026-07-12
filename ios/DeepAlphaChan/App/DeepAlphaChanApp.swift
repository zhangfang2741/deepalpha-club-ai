import SwiftUI

/// App 入口。持有全局的认证状态，根据是否登录切换根视图。
@main
struct DeepAlphaChanApp: App {
    @StateObject private var auth = AuthViewModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(auth)
                .tint(Theme.accent)
                .preferredColorScheme(.dark)
        }
    }
}
