import Foundation

/// 登录服务。后端 /auth/login 是 form-urlencoded（email/password/grant_type），
/// 这是与 spec 不同的实测结论——见实施计划「Spec 勘误」#1。
public struct AuthService: Sendable {
    let client: APIClient
    public init(client: APIClient) { self.client = client }

    public func login(email: String, password: String) async throws -> String {
        let resp: LoginResponse = try await client.postForm(
            "/api/v1/auth/login",
            fields: ["email": email, "password": password, "grant_type": "password"])
        return resp.accessToken
    }
}

/// 登录抽象（测试 mock）。真实现是上面的 AuthService struct。
public protocol AuthServiceProtocol: Sendable {
    func login(email: String, password: String) async throws -> String
}

extension AuthService: AuthServiceProtocol {}
