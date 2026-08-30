import Foundation

/// 认证抽象（测试 mock）。真实现是下面的 AuthService struct。
public protocol AuthServiceProtocol: Sendable {
    /// 邮箱 + 密码登录（form-urlencoded 的老端点，保留兼容）。
    func login(email: String, password: String) async throws -> String
    /// 统一登录：account 可以是手机号或邮箱，由服务端判别。
    func login(account: String, password: String) async throws -> String

    func requestRegisterCode(account: String, channel: AccountChannel) async throws
    func register(account: String, channel: AccountChannel, code: String,
                  password: String, username: String?) async throws -> String

    func requestPasswordResetCode(account: String, channel: AccountChannel) async throws
    func confirmPasswordReset(account: String, channel: AccountChannel,
                              code: String, newPassword: String) async throws
}

/// 认证接口封装。端点与后端 `app/api/v1/auth/routes.py` 一一对应。
public struct AuthService: Sendable {
    let client: APIClient
    public init(client: APIClient) { self.client = client }

    // MARK: - 登录

    /// 邮箱 + 密码：`/auth/login` 是 form-urlencoded（email/password/grant_type），
    /// 这是与 spec 不同的实测结论——见实施计划「Spec 勘误」#1。
    public func login(email: String, password: String) async throws -> String {
        let resp: LoginResponse = try await client.postForm(
            "/api/v1/auth/login",
            fields: ["email": email, "password": password, "grant_type": "password"])
        return resp.accessToken
    }

    /// 手机号或邮箱统一登录：类型由服务端 resolve_account 判别，前端只给一个输入框。
    public func login(account: String, password: String) async throws -> String {
        struct Body: Encodable {
            let account: String
            let password: String
        }
        let resp: LoginResponse = try await client.post(
            "/api/v1/auth/login/account", json: Body(account: account, password: password))
        return resp.accessToken
    }

    // MARK: - 注册

    /// 请求注册验证码。
    public func requestRegisterCode(account: String, channel: AccountChannel) async throws {
        switch channel {
        case .email:
            struct Body: Encodable { let email: String }
            let _: SentResponse = try await client.post(
                "/api/v1/auth/register/request-code", json: Body(email: account))
        case .phone:
            struct Body: Encodable { let phone: String }
            let _: SentResponse = try await client.post(
                "/api/v1/auth/phone/register/request-code", json: Body(phone: account))
        }
    }

    /// 校验验证码并注册，返回 access token（注册即登录）。
    public func register(account: String, channel: AccountChannel, code: String,
                         password: String, username: String?) async throws -> String {
        // 空用户名当没填：后端 username 可空，发空串反而会存下一个空名字
        let name = (username?.isEmpty == false) ? username : nil
        switch channel {
        case .email:
            struct Body: Encodable {
                let email: String
                let code: String
                let password: String
                let username: String?
            }
            let resp: RegisterResponse = try await client.post(
                "/api/v1/auth/register/verify",
                json: Body(email: account, code: code, password: password, username: name))
            return resp.token.accessToken
        case .phone:
            struct Body: Encodable {
                let phone: String
                let code: String
                let password: String
                let username: String?
            }
            let resp: RegisterResponse = try await client.post(
                "/api/v1/auth/phone/register",
                json: Body(phone: account, code: code, password: password, username: name))
            return resp.token.accessToken
        }
    }

    // MARK: - 找回密码

    /// 请求找回密码验证码。
    ///
    /// 注意：无论账号是否存在服务端都返回成功（防账号枚举），所以这个调用成功
    /// 不代表账号存在，UI 上不能据此提示「账号已找到」。
    public func requestPasswordResetCode(account: String, channel: AccountChannel) async throws {
        switch channel {
        case .email:
            struct Body: Encodable { let email: String }
            let _: SentResponse = try await client.post(
                "/api/v1/auth/password-reset/request", json: Body(email: account))
        case .phone:
            struct Body: Encodable { let phone: String }
            let _: SentResponse = try await client.post(
                "/api/v1/auth/phone/password-reset/request", json: Body(phone: account))
        }
    }

    /// 凭验证码设置新密码。
    public func confirmPasswordReset(account: String, channel: AccountChannel,
                                     code: String, newPassword: String) async throws {
        switch channel {
        case .email:
            struct Body: Encodable {
                let email: String
                let code: String
                let new_password: String
            }
            let _: ResetResponse = try await client.post(
                "/api/v1/auth/password-reset/confirm",
                json: Body(email: account, code: code, new_password: newPassword))
        case .phone:
            struct Body: Encodable {
                let phone: String
                let code: String
                let new_password: String
            }
            let _: ResetResponse = try await client.post(
                "/api/v1/auth/phone/password-reset/confirm",
                json: Body(phone: account, code: code, new_password: newPassword))
        }
    }
}

extension AuthService: AuthServiceProtocol {}
