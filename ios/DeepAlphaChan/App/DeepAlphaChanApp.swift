import SwiftUI

/// App 入口。持有全局的认证状态，根据是否登录切换根视图。
@main
struct DeepAlphaChanApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    @StateObject private var auth = AuthViewModel()
    @StateObject private var store = StoreManager()
    @StateObject private var usage = UsageTracker()
    @StateObject private var orientation = AppOrientation()
    @StateObject private var localization = LocalizationManager.shared

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(auth)
                .environmentObject(store)
                .environmentObject(usage)
                .environmentObject(orientation)
                .environmentObject(localization)
                // 切换语言时把新 locale 注入环境，所有系统格式化随之走对应语言；
                // 再用 .id 强制整棵视图树重建，确保缓存了旧语言的视图也刷新。
                .environment(\.locale, localization.locale)
                .id(localization.language)
                .tint(Theme.accent)
                .preferredColorScheme(.dark)
                // AppDelegate 是 UIKit 侧的，拿不到 SwiftUI 的 @StateObject，
                // 用一个静态引用把同一个实例递过去。
                .onAppear { AppDelegate.orientation = orientation }
        }
    }
}

// 原先这里有个 ShareCardSelfTest：带 -shareCardSelfTest 启动参数就用假数据渲染一张
// 精排分享卡写进 Documents。随精排卡一并删除 —— 新方案截的是真实屏幕，脱离运行中的
// 界面就无从自检，假数据也构造不出来。
