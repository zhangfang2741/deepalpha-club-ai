// ViewModels/SettingsViewModel.swift
import Foundation

@MainActor
final class SettingsViewModel: ObservableObject {
    @Published var profile: UserProfile?
    @Published var isLoadingProfile = false
    @Published var profileErrorMessage: String?

    @Published var isChangingPassword = false
    @Published var passwordErrorMessage: String?
    @Published var passwordSuccessMessage: String?

    @Published var isDeletingAccount = false
    @Published var deleteErrorMessage: String?

    func loadProfile() async {
        isLoadingProfile = true
        profileErrorMessage = nil
        defer { isLoadingProfile = false }
        do {
            profile = try await AuthService.me()
        } catch {
            profileErrorMessage = L("账户信息加载失败")
        }
    }

    func changePassword(oldPassword: String, newPassword: String) async -> Bool {
        isChangingPassword = true
        passwordErrorMessage = nil
        passwordSuccessMessage = nil
        defer { isChangingPassword = false }
        do {
            try await AuthService.changePassword(oldPassword: oldPassword, newPassword: newPassword)
            passwordSuccessMessage = L("密码修改成功")
            return true
        } catch let error as APIError {
            passwordErrorMessage = error.message
            return false
        } catch {
            passwordErrorMessage = L("修改密码失败，请稍后再试")
            return false
        }
    }

    /// 删除账号。成功返回 true，由调用方负责登出跳回登录页。
    ///
    /// 失败不登出：密码输错、断网都该留在原地让用户重试，把人踢回登录页
    /// 反而会让人以为「是不是已经删了」。
    func deleteAccount(password: String) async -> Bool {
        isDeletingAccount = true
        deleteErrorMessage = nil
        defer { isDeletingAccount = false }
        do {
            try await AuthService.deleteAccount(password: password)
            return true
        } catch let error as APIError {
            deleteErrorMessage = error.message
            return false
        } catch {
            deleteErrorMessage = L("删除账号失败，请稍后再试")
            return false
        }
    }
}
