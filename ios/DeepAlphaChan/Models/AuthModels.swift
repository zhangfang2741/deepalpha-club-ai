import Foundation

/// 登录响应：对应后端 `POST /api/v1/auth/login`，仅含 token。
struct LoginResponse: Codable {
    let accessToken: String
    let tokenType: String
    let expiresAt: String

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case tokenType = "token_type"
        case expiresAt = "expires_at"
    }
}

/// 注册响应：对应带验证码的注册端点，含用户信息与嵌套 token。
/// email 与 phone 都可空——手机号注册的用户没有邮箱，反之亦然。
struct RegisterResponse: Codable {
    let id: Int
    let email: String?
    let phone: String?
    let username: String?
    let token: LoginResponse
}

/// 当前用户资料：对应 `GET /api/v1/auth/me`。
struct UserProfile: Codable, Identifiable {
    let id: Int
    let email: String?
    let phone: String?
    let username: String?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, email, phone, username
        case createdAt = "created_at"
    }

    /// 展示用的账号：优先邮箱，其次打码手机号。
    var displayAccount: String {
        if let email, !email.isEmpty { return email }
        if let phone, !phone.isEmpty { return Self.masked(phone) }
        return "—"
    }

    /// +8613800138000 → 138****8000。号码属于个人信息，界面上不必完整显示。
    static func masked(_ e164: String) -> String {
        let digits = e164.hasPrefix("+86") ? String(e164.dropFirst(3)) : e164
        guard digits.count >= 8 else { return digits }
        let head = digits.prefix(digits.count - 8)
        let mid = digits.dropFirst(digits.count - 8).prefix(3)
        let tail = digits.suffix(4)
        return "\(head)\(mid)****\(tail)"
    }
}

// MARK: - 双通道注册 / 登录 / 找回密码

/// 发码类接口的响应：`{"sent": true}`
struct SentResponse: Codable {
    let sent: Bool
}

/// 重置密码的响应：`{"reset": true}`
struct ResetResponse: Codable {
    let reset: Bool
}
