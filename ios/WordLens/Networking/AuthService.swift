// Networking/AuthService.swift
import Foundation

/// WordLens 独立账号的注册/登录，对应后端 /vocabulary/auth/*。
enum AuthService {
    static func register(email: String, password: String) async throws -> AuthTokenResponse {
        struct Body: Encodable { let email: String; let password: String }
        return try await APIClient.shared.postJSON("/auth/register", body: Body(email: email, password: password))
    }

    static func login(email: String, password: String) async throws -> AuthTokenResponse {
        struct Body: Encodable { let email: String; let password: String }
        return try await APIClient.shared.postJSON("/auth/login", body: Body(email: email, password: password))
    }

    static func me() async throws -> UserProfile {
        try await APIClient.shared.get("/auth/me")
    }

    static func changePassword(oldPassword: String, newPassword: String) async throws {
        struct Body: Encodable { let oldPassword: String; let newPassword: String
            enum CodingKeys: String, CodingKey { case oldPassword = "old_password"; case newPassword = "new_password" }
        }
        let _: ChangePasswordResponse = try await APIClient.shared.postJSON(
            "/auth/change-password", body: Body(oldPassword: oldPassword, newPassword: newPassword)
        )
    }

    /// 请求给邮箱发一个找回密码的验证码。
    ///
    /// 后端对「邮箱未注册」也返回成功（防账号枚举），所以这里拿到 200
    /// 不代表该邮箱一定存在，UI 文案要按「如果该邮箱已注册，验证码已发出」来写。
    static func requestPasswordReset(email: String) async throws {
        struct Body: Encodable { let email: String }
        let _: PasswordResetSentResponse = try await APIClient.shared.postJSON(
            "/auth/password-reset/request", body: Body(email: email)
        )
    }

    /// 凭验证码设置新密码。
    static func confirmPasswordReset(email: String, code: String, newPassword: String) async throws {
        struct Body: Encodable {
            let email: String
            let code: String
            let newPassword: String
            enum CodingKeys: String, CodingKey {
                case email, code
                case newPassword = "new_password"
            }
        }
        let _: PasswordResetDoneResponse = try await APIClient.shared.postJSON(
            "/auth/password-reset/confirm",
            body: Body(email: email, code: code, newPassword: newPassword)
        )
    }

    /// 彻底删除账号及全部数据，需带当前密码二次确认。不可恢复。
    ///
    /// 用 POST 而不是 DELETE：带 body 的 DELETE 语义未定义，部分代理会丢掉 body，
    /// 而这里必须把密码传给后端校验。
    static func deleteAccount(password: String) async throws {
        struct Body: Encodable { let password: String }
        let _: DeleteAccountResponse = try await APIClient.shared.postJSON(
            "/auth/delete-account", body: Body(password: password)
        )
    }
}
