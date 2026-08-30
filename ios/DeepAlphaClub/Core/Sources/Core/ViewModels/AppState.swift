import Foundation
import Observation

/// 全局登录态：token 存 Keychain，启动恢复；401 时任何模块调 handleUnauthorized。
@MainActor @Observable
public final class AppState {
    public private(set) var token: String?
    public var authError: String?
    public private(set) var loggingIn = false
    /// token 没能写进 Keychain 时的提示（登录本身是成功的，只是不持久）。
    /// 可写：视图关掉提示条时置 nil，与 authError 同待遇。
    public var persistenceWarning: String?

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
            finishAuth(token: t)
            return true
        } catch let e as APIError {
            authError = e.message
        } catch {
            authError = "登录失败：\(error.localizedDescription)"
        }
        return false
    }

    // MARK: - 双通道登录 / 注册 / 找回密码

    /// 统一登录：account 是手机号或邮箱，类型由服务端判别。
    @discardableResult
    public func login(account: String, password: String) async -> Bool {
        guard !account.isEmpty, !password.isEmpty else {
            authError = "请输入账号和密码"
            return false
        }
        return await perform { [self] in
            let t = try await auth.login(account: account, password: password)
            finishAuth(token: t)
        }
    }

    /// 请求注册验证码。返回 true 时界面才启动 60s 倒计时。
    @discardableResult
    public func requestRegisterCode(account: String, channel: AccountChannel) async -> Bool {
        await perform { [self] in
            try await auth.requestRegisterCode(account: account, channel: channel)
        }
    }

    /// 注册即登录：后端在验码建号后直接下发 token。
    @discardableResult
    public func register(account: String, channel: AccountChannel, code: String,
                         password: String, username: String?) async -> Bool {
        await perform { [self] in
            let t = try await auth.register(account: account, channel: channel, code: code,
                                            password: password, username: username)
            finishAuth(token: t)
        }
    }

    /// 请求找回密码验证码。
    ///
    /// 服务端对未注册账号也返回成功（防账号枚举），所以返回 true 不代表账号存在，
    /// UI 不能据此提示「账号已找到」。
    @discardableResult
    public func requestPasswordResetCode(account: String, channel: AccountChannel) async -> Bool {
        await perform { [self] in
            try await auth.requestPasswordResetCode(account: account, channel: channel)
        }
    }

    /// 重置密码。成功后**不**自动登录——密码已变，让用户用新密码走一遍登录。
    @discardableResult
    public func resetPassword(account: String, channel: AccountChannel,
                              code: String, newPassword: String) async -> Bool {
        await perform { [self] in
            try await auth.confirmPasswordReset(account: account, channel: channel,
                                                code: code, newPassword: newPassword)
        }
    }

    // MARK: - 内部

    /// 拿到 token 后的共同收尾：落 Keychain + 置登录态。
    ///
    /// Keychain 写失败**不算登录失败**：token 已经到手，本次会话的所有请求都能用，
    /// 代价只是下次启动要重登。模拟器缺 keychain entitlement 时 SecItemAdd 会返回
    /// -34018，若在这里抛错，用户会看到「登录失败」而其实后端已经认证通过了。
    private func finishAuth(token t: String) {
        do {
            try keychain.saveToken(t)
            persistenceWarning = nil
        } catch {
            persistenceWarning = "登录成功，但登录状态没能保存，下次启动需要重新登录"
        }
        token = t
    }

    /// 包住 loggingIn / authError 的样板：六个入口各写一遍 do-catch 太吵。
    private func perform(_ body: () async throws -> Void) async -> Bool {
        authError = nil
        loggingIn = true
        defer { loggingIn = false }
        do {
            try await body()
            return true
        } catch let e as APIError {
            authError = e.message
        } catch {
            authError = "操作失败：\(error.localizedDescription)"
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
