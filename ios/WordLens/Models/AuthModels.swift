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
