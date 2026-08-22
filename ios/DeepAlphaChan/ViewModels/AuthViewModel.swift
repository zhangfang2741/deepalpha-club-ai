import Foundation
import SwiftUI

/// 「保持登录」的存储键。放在类型外面：@AppStorage 是存储属性，
/// 它的初始化器里引用不了 Self。
private let rememberMeKey = "remember_me"

/// 全局认证状态。
///
/// 「保持登录」的语义：勾选时 token 留在 Keychain，下次启动直接进主页（这是
/// 改造前唯一的行为）；不勾选时启动即清 token，必须重新登录。判断放在 init 里
/// 而不是 logout 里，因为要覆盖的正是「上次没勾、App 被杀掉后重新打开」这种情况。
@MainActor
final class AuthViewModel: ObservableObject {
    @Published var isAuthenticated: Bool
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var profile: UserProfile?

    /// 保持登录。默认开——绝大多数用户不希望每次打开都登录一遍。
    @AppStorage(rememberMeKey) var rememberMe: Bool = true

    init() {
        // @AppStorage 在 init 里还不能读，直接查 UserDefaults。键名共用同一个常量。
        let remembered =
            UserDefaults.standard.object(forKey: rememberMeKey) as? Bool ?? true
        if !remembered {
            KeychainStore.clearToken()
        }
        self.isAuthenticated = KeychainStore.loadToken() != nil
    }

    // MARK: - 登录

    func login(account: String, password: String) async {
        guard !account.isEmpty, !password.isEmpty else {
            errorMessage = "请输入账号和密码"
            return
        }
        await perform(fallback: "登录失败，请稍后再试") {
            let resp = try await AuthService.login(account: account, password: password)
            self.finishAuth(token: resp.accessToken)
        }
    }

    /// Sign in with Apple：用 Apple 身份令牌登录。
    func loginWithApple(identityToken: String, fullName: String?) async {
        await perform(fallback: "Apple 登录失败，请稍后再试") {
            let resp = try await AuthService.appleLogin(
                identityToken: identityToken, fullName: fullName)
            self.finishAuth(token: resp.accessToken)
        }
    }

    // MARK: - 注册

    /// 请求注册验证码。成功返回 true，供界面启动倒计时。
    func requestRegisterCode(account: String, channel: AccountChannel) async -> Bool {
        await performBool(fallback: "验证码发送失败，请稍后再试") {
            try await AuthService.requestRegisterCode(account: account, channel: channel)
        }
    }

    func register(
        account: String, channel: AccountChannel, code: String,
        password: String, username: String?
    ) async {
        await perform(fallback: "注册失败，请稍后再试") {
            let resp = try await AuthService.register(
                account: account, channel: channel, code: code,
                password: password,
                username: (username?.isEmpty == false) ? username : nil)
            self.finishAuth(token: resp.token.accessToken)
        }
    }

    // MARK: - 找回密码

    func requestPasswordResetCode(account: String, channel: AccountChannel) async -> Bool {
        await performBool(fallback: "验证码发送失败，请稍后再试") {
            try await AuthService.requestPasswordResetCode(account: account, channel: channel)
        }
    }

    /// 重置密码。成功返回 true，界面据此关闭页面并提示去登录。
    func resetPassword(
        account: String, channel: AccountChannel, code: String, newPassword: String
    ) async -> Bool {
        await performBool(fallback: "重置密码失败，请稍后再试") {
            try await AuthService.confirmPasswordReset(
                account: account, channel: channel, code: code, newPassword: newPassword)
        }
    }

    // MARK: - 账号

    func loadProfile() async {
        profile = try? await AuthService.me()
    }

    func logout() {
        KeychainStore.clearToken()
        profile = nil
        isAuthenticated = false
    }

    /// 删除账号：成功后本地登出。
    func deleteAccount() async -> Bool {
        await performBool(fallback: "删除账号失败，请稍后再试") {
            try await AuthService.deleteAccount()
            self.logout()
        }
    }

    // MARK: - 内部

    /// 登录成功后的共同收尾：存 token、置状态、拉资料。
    ///
    /// 不勾「保持登录」时仍然写 Keychain，因为本次会话的所有请求都要靠它取 token；
    /// 区别在于下次启动时 init 会把它清掉。
    private func finishAuth(token: String) {
        KeychainStore.saveToken(token)
        isAuthenticated = true
        Task { await loadProfile() }
    }

    /// 包住 isLoading / errorMessage 的样板。九个入口各写一遍 do-catch 太吵。
    private func perform(fallback: String, _ body: @escaping () async throws -> Void) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            try await body()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = fallback
        }
    }

    @discardableResult
    private func performBool(
        fallback: String, _ body: @escaping () async throws -> Void
    ) async -> Bool {
        var ok = false
        await perform(fallback: fallback) {
            try await body()
            ok = true
        }
        return ok
    }
}
