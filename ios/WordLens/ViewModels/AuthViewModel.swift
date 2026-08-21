// ViewModels/AuthViewModel.swift
import Foundation

@MainActor
final class AuthViewModel: ObservableObject {
    @Published var isAuthenticated: Bool
    @Published var isLoading = false
    @Published var errorMessage: String?

    init() {
        self.isAuthenticated = KeychainStore.loadToken() != nil
        Task { [weak self] in
            for await _ in NotificationCenter.default.notifications(named: .apiUnauthorized) {
                self?.logout()
            }
        }
    }

    /// 切换登录方式等场景下清掉上一次的报错，避免旧错误文案挂在新表单上。
    func clearError() { errorMessage = nil }

    // MARK: - 手机号

    /// 给待注册手机号发验证码。成功返回 true，调用方据此进入第二步。
    func requestPhoneRegisterCode(phone: String) async -> Bool {
        await runCodeRequest(empty: phone.isEmpty, emptyMessage: L("请输入手机号")) {
            try await AuthService.requestPhoneRegisterCode(phone: phone)
        }
    }

    func registerByPhone(phone: String, password: String, code: String) async {
        await runAuth(fallback: L("注册失败，请稍后再试")) {
            try await AuthService.registerByPhone(phone: phone, password: password, code: code)
        }
    }

    func loginByPhone(phone: String, password: String) async {
        guard !phone.isEmpty, !password.isEmpty else {
            errorMessage = L("请输入手机号和密码")
            return
        }
        await runAuth(fallback: L("登录失败，请稍后再试")) {
            try await AuthService.loginByPhone(phone: phone, password: password)
        }
    }

    func requestPhonePasswordReset(phone: String) async -> Bool {
        await runCodeRequest(empty: phone.isEmpty, emptyMessage: L("请输入手机号")) {
            try await AuthService.requestPhonePasswordReset(phone: phone)
        }
    }

    func confirmPhonePasswordReset(phone: String, code: String, newPassword: String) async -> Bool {
        await runCodeRequest(empty: false, emptyMessage: "") {
            try await AuthService.confirmPhonePasswordReset(
                phone: phone, code: code, newPassword: newPassword
            )
        }
    }

    // MARK: - 公共执行壳
    //
    // 这几个流程的骨架完全一样（置 loading → 调接口 → APIError 透传后端文案 →
    // 其它异常给兜底文案），抽出来避免每个方法复制一遍同样的 do/catch。

    private func runAuth(fallback: String, _ body: () async throws -> AuthTokenResponse) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let resp = try await body()
            KeychainStore.saveToken(resp.accessToken)
            isAuthenticated = true
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = fallback
        }
    }

    private func runCodeRequest(
        empty: Bool, emptyMessage: String, _ body: () async throws -> Void
    ) async -> Bool {
        guard !empty else {
            errorMessage = emptyMessage
            return false
        }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            try await body()
            return true
        } catch let error as APIError {
            errorMessage = error.message
            return false
        } catch {
            errorMessage = L("操作失败，请检查网络后重试")
            return false
        }
    }

    // MARK: - 邮箱

    /// 给待注册邮箱发验证码。成功返回 true，调用方据此进入第二步。
    func requestRegisterCode(email: String) async -> Bool {
        guard !email.isEmpty else {
            errorMessage = L("请输入邮箱")
            return false
        }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            try await AuthService.requestRegisterCode(email: email)
            return true
        } catch let error as APIError {
            errorMessage = error.message
            return false
        } catch {
            errorMessage = L("验证码发送失败，请稍后再试")
            return false
        }
    }

    func register(email: String, password: String, code: String) async {
        guard !email.isEmpty, !password.isEmpty else {
            errorMessage = L("请输入邮箱和密码")
            return
        }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let resp = try await AuthService.register(email: email, password: password, code: code)
            KeychainStore.saveToken(resp.accessToken)
            isAuthenticated = true
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = L("注册失败，请稍后再试")
        }
    }

    func login(email: String, password: String) async {
        guard !email.isEmpty, !password.isEmpty else {
            errorMessage = L("请输入邮箱和密码")
            return
        }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let resp = try await AuthService.login(email: email, password: password)
            KeychainStore.saveToken(resp.accessToken)
            isAuthenticated = true
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = L("登录失败，请稍后再试")
        }
    }

    func logout() {
        KeychainStore.clearToken()
        isAuthenticated = false
    }
}
