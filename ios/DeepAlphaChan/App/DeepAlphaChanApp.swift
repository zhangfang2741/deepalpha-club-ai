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

    #if DEBUG
    @State private var demoLoginStarted = false
    #endif

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
                #if DEBUG
                .task {
                    await runDemoLoginIfRequested()
                }
                #endif
        }
    }

    #if DEBUG
    /// 仅供模拟器录制使用。账号通过 Debug 启动参数注入，不进入源码或生产包。
    private func runDemoLoginIfRequested() async {
        guard !demoLoginStarted,
              ProcessInfo.processInfo.arguments.contains("-deepalphaDemo"),
              !auth.isAuthenticated,
              let account = demoArgument(named: "deepalphaDemoAccount"),
              let password = demoArgument(named: "deepalphaDemoPassword"),
              !account.isEmpty, !password.isEmpty else { return }
        demoLoginStarted = true
        await auth.login(account: account, password: password)
    }

    private func demoArgument(named name: String) -> String? {
        let prefix = "-\(name)="
        return ProcessInfo.processInfo.arguments
            .first(where: { $0.hasPrefix(prefix) })
            .map { String($0.dropFirst(prefix.count)) }
    }
    #endif
}

// 原先这里有个 ShareCardSelfTest：带 -shareCardSelfTest 启动参数就用假数据渲染一张
// 精排分享卡写进 Documents。随精排卡一并删除 —— 新方案截的是真实屏幕，脱离运行中的
// 界面就无从自检，假数据也构造不出来。
