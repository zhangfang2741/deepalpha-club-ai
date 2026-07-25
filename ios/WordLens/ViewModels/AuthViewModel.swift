// ViewModels/AuthViewModel.swift
import Foundation

@MainActor
final class AuthViewModel: ObservableObject {
    @Published var isAuthenticated: Bool
    @Published var isLoading = false
    @Published var errorMessage: String?

    init() {
        self.isAuthenticated = KeychainStore.loadToken() != nil
    }

    func register(email: String, password: String) async {
        guard !email.isEmpty, !password.isEmpty else {
            errorMessage = "请输入邮箱和密码"
            return
        }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let resp = try await AuthService.register(email: email, password: password)
            KeychainStore.saveToken(resp.accessToken)
            isAuthenticated = true
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "注册失败，请稍后再试"
        }
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
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "登录失败，请稍后再试"
        }
    }

    func logout() {
        KeychainStore.clearToken()
        isAuthenticated = false
    }
}
