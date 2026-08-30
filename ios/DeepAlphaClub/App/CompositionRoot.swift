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

    private static func makeKeychain() -> any KeychainStoring {
        KeychainStore()
    }

    /// DEBUG 下从环境变量取自动登录凭据，供模拟器冒烟用（见 README）：
    /// `SIMCTL_CHILD_DEBUG_ACCOUNT=… SIMCTL_CHILD_DEBUG_PASSWORD=… xcrun simctl launch …`
    /// Release 构建恒为 nil，凭据不会进二进制。
    static var debugCredentials: (account: String, password: String)? {
        #if DEBUG
        let env = ProcessInfo.processInfo.environment
        guard let account = env["DEBUG_ACCOUNT"], let password = env["DEBUG_PASSWORD"],
              !account.isEmpty, !password.isEmpty else { return nil }
        return (account, password)
        #else
        return nil
        #endif
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
