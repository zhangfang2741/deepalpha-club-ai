// Models/AuthModels.swift
import Foundation

/// 对应后端 VocabularyTokenResponse（注册/登录成功后的响应）。
struct AuthTokenResponse: Codable {
    let accessToken: String
    let tokenType: String
    let expiresAt: String

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case tokenType = "token_type"
        case expiresAt = "expires_at"
    }
}

/// 对应后端 VocabularyUserResponse（当前用户个人信息）。
struct UserProfile: Codable {
    let id: String
    let email: String
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, email
        case createdAt = "created_at"
    }
}

/// 对应后端 /auth/change-password 响应（{"changed": true}）。
struct ChangePasswordResponse: Codable {
    let changed: Bool
}

/// 对应后端 /auth/delete-account 响应（{"deleted": true}）。
struct DeleteAccountResponse: Codable {
    let deleted: Bool
}

/// 对应后端 /auth/password-reset/request 响应（{"sent": true}）。
struct PasswordResetSentResponse: Codable {
    let sent: Bool
}

/// 对应后端 /auth/password-reset/confirm 响应（{"reset": true}）。
struct PasswordResetDoneResponse: Codable {
    let reset: Bool
}
