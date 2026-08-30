import SwiftUI
import DeepAlphaCore

@main
struct DeepAlphaClubApp: App {
    @State private var root = CompositionRoot()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(\.compositionRoot, root)
                .environment(root.appState)
                .environment(root.deskVM)
                .environment(root.historyVM)
                .task {
                    // 「保持登录」没勾时，上次留下的 token 不该跨启动生效。
                    // 用 object(forKey:) 取而不是 bool(forKey:)：后者在「从未设置过」
                    // 时返回 false，会把默认开启的行为误判成关闭。
                    let remembered =
                        UserDefaults.standard.object(forKey: "remember_me") as? Bool ?? true
                    if !remembered { root.appState.logout() }
                    root.appState.restoreFromKeychain()

                    // 冒烟用：DEBUG 且给了环境变量凭据时跳过手工登录
                    if !root.appState.isLoggedIn,
                       let cred = CompositionRoot.debugCredentials {
                        await root.appState.login(account: cred.account,
                                                  password: cred.password)
                    }
                }
        }
        .onChange(of: scenePhase) { _, phase in
            switch phase {
            case .background:
                root.deskVM.appDidEnterBackground()
            case .active:
                Task { await root.deskVM.appDidBecomeActive() }
            default:
                break
            }
        }
    }
}
