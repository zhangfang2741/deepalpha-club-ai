import Foundation
import SwiftUI
import DeepAlphaCore

/// 全部依赖在此组装（视图层不直接 new service）。
/// 注意：本身非 Observable，不能用 @Environment(Self.self) 注入——
/// 用文件末尾的 EnvironmentKey（\.compositionRoot）。
/// 用 @MainActor final class 而非 struct：EnvironmentKey.defaultValue 是 nonisolated static，
/// 要求 Value 满足 Sendable；MainActor 隔离的 class 天然 Sendable。
@MainActor
final class CompositionRoot {
    /// 后端地址。本地联调改这里（如 http://localhost:8000，需同时加 ATS 例外）。
    static let apiBaseURL = URL(string: "https://api.deepalpha.club")!

    let keychain: any KeychainStoring
    let appState: AppState
    let deskVM: TradingDeskViewModel
    let historyVM: HistoryListViewModel
    /// 回放 VM 每次进详情页新建（runId 由 load(runId:) 传，不在 init）。
    let replayFactory: @MainActor () -> RunReplayViewModel

    init() {
        let keychain = Self.makeKeychain()
        let api = APIClient(baseURL: Self.apiBaseURL) { keychain.loadToken() }
        let sse = SSEClient(baseURL: Self.apiBaseURL) { keychain.loadToken() }
        let service = TradingDeskService(api: api, sse: sse)
        let auth = AuthService(client: api)

        self.keychain = keychain
        self.appState = AppState(keychain: keychain, auth: auth)
        self.deskVM = TradingDeskViewModel(service: service)
        self.historyVM = HistoryListViewModel(
            service: service,
            cache: RunCacheDefault.make())
        self.replayFactory = { RunReplayViewModel(service: service) }
    }

    /// 正常走真 Keychain。DEBUG 且带环境变量 `DEBUG_FAKE_LOGIN=1` 时改用内存实现并预置
    /// 一个假 token —— 只为在没有账号的机器上冒烟验证登录后的布局，
    /// 假 token 对后端无效（任何请求都会 401），也不落盘。
    private static func makeKeychain() -> any KeychainStoring {
        #if DEBUG
        if ProcessInfo.processInfo.environment["DEBUG_FAKE_LOGIN"] == "1" {
            let memory = InMemoryKeychain()
            try? memory.saveToken("debug-fake-token")
            return memory
        }
        #endif
        return KeychainStore()
    }
}

private struct CompositionRootKey: EnvironmentKey {
    static let defaultValue: CompositionRoot? = nil
}

extension EnvironmentValues {
    /// 非 Observable 的组合根用 EnvironmentKey 注入（@Environment(Self.self) 只支持 Observable）。
    var compositionRoot: CompositionRoot? {
        get { self[CompositionRootKey.self] }
        set { self[CompositionRootKey.self] = newValue }
    }
}
