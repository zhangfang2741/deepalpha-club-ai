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

/// 当前用户资料：对应 `GET /api/v1/auth/me`。
struct UserProfile: Codable, Identifiable {
    let id: Int
    let email: String
    let username: String?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, email, username
        case createdAt = "created_at"
    }
}
