import Foundation

/// 登录响应（`/auth/login`、`/auth/login/account` 共用，只取 access_token）。
public struct LoginResponse: Codable, Sendable, Equatable {
    public var accessToken: String
    enum CodingKeys: String, CodingKey { case accessToken = "access_token" }
}

/// 注册响应：含用户信息与嵌套 token。
/// email 与 phone 都可空——手机号注册的用户没有邮箱，反之亦然。
public struct RegisterResponse: Codable, Sendable, Equatable {
    public var id: Int
    public var email: String?
    public var phone: String?
    public var username: String?
    public var token: LoginResponse
}

/// 发码类接口的响应：`{"sent": true}`
public struct SentResponse: Codable, Sendable, Equatable {
    public var sent: Bool
}

/// 重置密码的响应：`{"reset": true}`
public struct ResetResponse: Codable, Sendable, Equatable {
    public var reset: Bool
}

/// 当前用户资料：`GET /api/v1/auth/me`。
public struct UserProfile: Codable, Sendable, Equatable, Identifiable {
    public var id: Int
    public var email: String?
    public var phone: String?
    public var username: String?
    public var createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, email, phone, username
        case createdAt = "created_at"
    }

    /// 展示用的账号：优先邮箱，其次打码手机号。
    public var displayAccount: String {
        if let email, !email.isEmpty { return email }
        if let phone, !phone.isEmpty { return Self.masked(phone) }
        return "—"
    }

    /// +8613800138000 → 138****8000。号码属于个人信息，界面上不必完整显示。
    public static func masked(_ e164: String) -> String {
        let digits = e164.hasPrefix("+86") ? String(e164.dropFirst(3)) : e164
        guard digits.count >= 8 else { return digits }
        let head = digits.prefix(digits.count - 8)
        let mid = digits.dropFirst(digits.count - 8).prefix(3)
        let tail = digits.suffix(4)
        return "\(head)\(mid)****\(tail)"
    }
}
