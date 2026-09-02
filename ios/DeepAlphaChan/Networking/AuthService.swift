import Foundation

/// 认证接口封装。
///
/// 从 ChanService.swift 拆出来：那个文件原本同时装着行情接口和认证接口，
/// 加上双通道注册后认证部分的体量已经超过行情部分。
enum AuthService {

    // MARK: - 登录

    /// 统一登录：account 可以是手机号或邮箱，由服务端判别。
    static func login(account: String, password: String) async throws -> LoginResponse {
        struct Body: Encodable {
            let account: String
            let password: String
        }
        return try await APIClient.shared.postJSON(
            "/auth/login/account", body: Body(account: account, password: password))
    }

    /// 运营商一键登录：把阿里云 AuthSDK 拿到的一次性 token 换成本平台 token。
    ///
    /// token 来自阿里云号码认证 SDK（通过运营商数据网络校验本机号码，App 全程接触
    /// 不到号码明文）。号码不存在则后端自动建号，存在则直接登录——一个入口同时
    /// 覆盖注册和登录。SDK 集成见 docs/superpowers/plans 里的一键登录说明。
    static func oneTapLogin(token: String, username: String? = nil) async throws -> LoginResponse {
        struct Body: Encodable {
            let token: String
            let username: String?
        }
        return try await APIClient.shared.postJSON(
            "/auth/phone/one-tap", body: Body(token: token, username: username))
    }

    /// Sign in with Apple：把 Apple 身份令牌换成本平台 token。
    static func appleLogin(identityToken: String, fullName: String?) async throws -> LoginResponse {
        struct Body: Encodable {
            let identity_token: String
            let full_name: String?
        }
        return try await APIClient.shared.postJSON("/auth/apple", body: Body(
            identity_token: identityToken, full_name: fullName))
    }

    // MARK: - 注册

    /// 请求注册验证码。
    @discardableResult
    static func requestRegisterCode(account: String, channel: AccountChannel) async throws -> SentResponse {
        switch channel {
        case .email:
            struct Body: Encodable { let email: String }
            return try await APIClient.shared.postJSON(
                "/auth/register/request-code", body: Body(email: account))
        case .phone:
            struct Body: Encodable { let phone: String }
            return try await APIClient.shared.postJSON(
                "/auth/phone/register/request-code", body: Body(phone: account))
        }
    }

    /// 校验验证码并注册。
    static func register(
        account: String, channel: AccountChannel, code: String,
        password: String, username: String?
    ) async throws -> RegisterResponse {
        switch channel {
        case .email:
            struct Body: Encodable {
                let email: String
                let code: String
                let password: String
                let username: String?
            }
            return try await APIClient.shared.postJSON("/auth/register/verify", body: Body(
                email: account, code: code, password: password, username: username))
        case .phone:
            struct Body: Encodable {
                let phone: String
                let code: String
                let password: String
                let username: String?
            }
            return try await APIClient.shared.postJSON("/auth/phone/register", body: Body(
                phone: account, code: code, password: password, username: username))
        }
    }

    // MARK: - 找回密码

    /// 请求找回密码验证码。
    ///
    /// 注意：无论账号是否存在服务端都返回成功（防账号枚举），所以这个调用成功
    /// 不代表账号存在，UI 上不能据此提示「账号已找到」。
    @discardableResult
    static func requestPasswordResetCode(
        account: String, channel: AccountChannel
    ) async throws -> SentResponse {
        switch channel {
        case .email:
            struct Body: Encodable { let email: String }
            return try await APIClient.shared.postJSON(
                "/auth/password-reset/request", body: Body(email: account))
        case .phone:
            struct Body: Encodable { let phone: String }
            return try await APIClient.shared.postJSON(
                "/auth/phone/password-reset/request", body: Body(phone: account))
        }
    }

    /// 凭验证码设置新密码。
    @discardableResult
    static func confirmPasswordReset(
        account: String, channel: AccountChannel, code: String, newPassword: String
    ) async throws -> ResetResponse {
        switch channel {
        case .email:
            struct Body: Encodable {
                let email: String
                let code: String
                let new_password: String
            }
            return try await APIClient.shared.postJSON(
                "/auth/password-reset/confirm",
                body: Body(email: account, code: code, new_password: newPassword))
        case .phone:
            struct Body: Encodable {
                let phone: String
                let code: String
                let new_password: String
            }
            return try await APIClient.shared.postJSON(
                "/auth/phone/password-reset/confirm",
                body: Body(phone: account, code: code, new_password: newPassword))
        }
    }

    // MARK: - 账号

    /// 获取当前用户资料。
    static func me() async throws -> UserProfile {
        try await APIClient.shared.get("/auth/me")
    }

    /// 删除当前账号（不可恢复）。App Store 5.1.1(v) 要求。
    @discardableResult
    static func deleteAccount() async throws -> MessageResponse {
        try await APIClient.shared.delete("/auth/me")
    }
}
