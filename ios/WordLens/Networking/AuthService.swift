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
