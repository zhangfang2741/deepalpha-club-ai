import SwiftUI

/// App 入口。持有全局的认证状态，根据是否登录切换根视图。
@main
struct DeepAlphaChanApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    @StateObject private var auth = AuthViewModel()
    @StateObject private var store = StoreManager()
    @StateObject private var usage = UsageTracker()
    @StateObject private var orientation = AppOrientation()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(auth)
                .environmentObject(store)
                .environmentObject(usage)
                .environmentObject(orientation)
                .tint(Theme.accent)
                .preferredColorScheme(.dark)
                // AppDelegate 是 UIKit 侧的，拿不到 SwiftUI 的 @StateObject，
                // 用一个静态引用把同一个实例递过去。
                .onAppear { AppDelegate.orientation = orientation }
        }
    }
}
