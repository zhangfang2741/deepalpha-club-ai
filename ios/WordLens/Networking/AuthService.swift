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
}
