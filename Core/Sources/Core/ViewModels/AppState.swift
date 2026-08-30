import Foundation
import Observation

/// 全局登录态：token 存 Keychain，启动恢复；401 时任何模块调 handleUnauthorized。
@MainActor @Observable
public final class AppState {
    public private(set) var token: String?
    public var authError: String?
    public private(set) var loggingIn = false

    public var isLoggedIn: Bool { token != nil }

    let keychain: any KeychainStoring
    let auth: any AuthServiceProtocol

    public init(keychain: any KeychainStoring, auth: any AuthServiceProtocol) {
        self.keychain = keychain
        self.auth = auth
    }

    /// App 启动时调用：Keychain 有 token 直接进主页。
    public func restoreFromKeychain() {
        token = keychain.loadToken()
    }

    @discardableResult
    public func login(email: String, password: String) async -> Bool {
        authError = nil
        loggingIn = true
        defer { loggingIn = false }
        guard !email.isEmpty, !password.isEmpty else {
            authError = "请输入邮箱和密码"
            return false
        }
        do {
            let t = try await auth.login(email: email, password: password)
            try keychain.saveToken(t)
            token = t
            return true
        } catch let e as APIError {
            authError = e.message
        } catch {
            authError = "登录失败：\(error.localizedDescription)"
        }
        return false
    }

    /// 401 全局处理：清 token，视图层观察到 isLoggedIn=false 自动回登录页。
    public func handleUnauthorized() {
        keychain.deleteToken()
        token = nil
    }

    public func logout() {
        keychain.deleteToken()
        token = nil
    }
}
