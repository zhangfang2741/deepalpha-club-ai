// ViewModels/SettingsViewModel.swift
import Foundation

@MainActor
final class SettingsViewModel: ObservableObject {
    @Published var profile: UserProfile?
    @Published var isLoadingProfile = false

    @Published var isChangingPassword = false
    @Published var passwordErrorMessage: String?
    @Published var passwordSuccessMessage: String?

    func loadProfile() async {
        isLoadingProfile = true
        defer { isLoadingProfile = false }
        profile = try? await AuthService.me()
    }

    func changePassword(oldPassword: String, newPassword: String) async -> Bool {
        isChangingPassword = true
        passwordErrorMessage = nil
        passwordSuccessMessage = nil
        defer { isChangingPassword = false }
        do {
            try await AuthService.changePassword(oldPassword: oldPassword, newPassword: newPassword)
            passwordSuccessMessage = "密码修改成功"
            return true
        } catch let error as APIError {
            passwordErrorMessage = error.message
            return false
        } catch {
            passwordErrorMessage = "修改密码失败，请稍后再试"
            return false
        }
    }
}
