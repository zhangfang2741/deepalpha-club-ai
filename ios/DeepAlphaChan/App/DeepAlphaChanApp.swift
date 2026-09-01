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
                .onAppear {
                    AppDelegate.orientation = orientation
                    #if DEBUG
                    ShareCardSelfTest.runIfRequested()
                    #endif
                }
        }
    }
}

#if DEBUG
/// 分享卡渲染自检（仅 DEBUG）。
///
/// 带 `-shareCardSelfTest` 启动参数时，用假数据渲染一张分享卡写进 Documents，
/// 便于在模拟器上直接验证离屏渲染管线，不必先登录再跑一遍分析。
enum ShareCardSelfTest {
    @MainActor
    static func runIfRequested() {
        guard ProcessInfo.processInfo.arguments.contains("-shareCardSelfTest") else { return }
        let vm = ChanViewModel()
        guard let image = ShareCardRenderer.render(analysis: PreviewMock.analysis,
                                                   vm: vm,
                                                   window: nil),
              let data = image.pngData() else {
            print("[selftest] 渲染失败")
            return
        }
        let url = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("share-card.png")
        try? data.write(to: url)
        print("[selftest] 已写入 \(url.path) 尺寸 \(image.size)")
    }
}
#endif
