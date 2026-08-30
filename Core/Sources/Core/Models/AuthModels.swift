import Foundation

/// POST /api/v1/auth/login 响应（只取 access_token，其余忽略）。
public struct LoginResponse: Codable, Sendable, Equatable {
    public var accessToken: String
    enum CodingKeys: String, CodingKey { case accessToken = "access_token" }
}
