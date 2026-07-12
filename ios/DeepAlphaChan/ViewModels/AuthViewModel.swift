import Foundation
import SwiftUI

/// 全局认证状态。启动时若 Keychain 有 token 即视为已登录。
@MainActor
final class AuthViewModel: ObservableObject {
    @Published var isAuthenticated: Bool
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var profile: UserProfile?

    init() {
        self.isAuthenticated = KeychainStore.loadToken() != nil
    }

    func login(email: String, password: String) async {
        guard !email.isEmpty, !password.isEmpty else {
            errorMessage = "请输入邮箱和密码"
            return
        }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let resp = try await AuthService.login(email: email, password: password)
            KeychainStore.saveToken(resp.accessToken)
            isAuthenticated = true
            await loadProfile()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "登录失败，请稍后再试"
        }
    }

    func register(email: String, password: String, username: String?) async {
        guard !email.isEmpty, !password.isEmpty else {
            errorMessage = "请输入邮箱和密码"
            return
        }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let resp = try await AuthService.register(
                email: email, password: password,
                username: username?.isEmpty == false ? username : nil)
            KeychainStore.saveToken(resp.token.accessToken)
            isAuthenticated = true
            await loadProfile()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "注册失败，请稍后再试"
        }
    }

    /// Sign in with Apple：用 Apple 身份令牌登录。
    func loginWithApple(identityToken: String, fullName: String?) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let resp = try await AuthService.appleLogin(identityToken: identityToken, fullName: fullName)
            KeychainStore.saveToken(resp.accessToken)
            isAuthenticated = true
            await loadProfile()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "Apple 登录失败，请稍后再试"
        }
    }

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
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            try await AuthService.deleteAccount()
            logout()
            return true
        } catch let error as APIError {
            errorMessage = error.message
            return false
        } catch {
            errorMessage = "删除账号失败，请稍后再试"
            return false
        }
    }
}
