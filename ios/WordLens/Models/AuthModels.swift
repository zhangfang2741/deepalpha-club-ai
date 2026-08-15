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
    /// 邮箱注册的账号才有；手机号注册的为 nil。
    let email: String?
    /// 手机号注册的账号才有；邮箱注册的为 nil。E.164 格式。
    let phone: String?
    let createdAt: String

    /// 账户概览里展示的登录标识。两者至少有一个（后端有 CHECK 约束保证）。
    var displayIdentifier: String {
        email ?? phone.map(Self.masked) ?? "—"
    }

    /// 手机号打码展示：+8613800138000 → 138****8000。
    /// 设置页会在别人也能看到屏幕的场合打开，完整号码没必要一直亮着。
    private static func masked(_ e164: String) -> String {
        let digits = e164.hasPrefix("+86") ? String(e164.dropFirst(3)) : e164
        guard digits.count >= 7 else { return digits }
        return "\(digits.prefix(3))****\(digits.suffix(4))"
    }

    enum CodingKeys: String, CodingKey {
        case id, email, phone
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

/// 对应后端 /auth/register/request-code 响应（{"sent": true}）。
struct RegisterCodeSentResponse: Codable {
    let sent: Bool
}

/// 对应后端 /auth/password-reset/request 响应（{"sent": true}）。
struct PasswordResetSentResponse: Codable {
    let sent: Bool
}

/// 对应后端 /auth/password-reset/confirm 响应（{"reset": true}）。
struct PasswordResetDoneResponse: Codable {
    let reset: Bool
}
