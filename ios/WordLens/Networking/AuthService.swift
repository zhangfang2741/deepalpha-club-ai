// Networking/AuthService.swift
import Foundation

/// WordLens 独立账号的注册/登录，对应后端 /vocabulary/auth/*。
enum AuthService {
    /// 请求给待注册邮箱发验证码。邮箱已被注册时后端返回 400，会带出明确文案。
    static func requestRegisterCode(email: String) async throws {
        struct Body: Encodable { let email: String }
        let _: RegisterCodeSentResponse = try await APIClient.shared.postJSON(
            "/auth/register/request-code", body: Body(email: email)
        )
    }

    /// 凭邮箱验证码完成注册。验码通过后后端才会真正建号。
    static func register(email: String, password: String, code: String) async throws -> AuthTokenResponse {
        struct Body: Encodable { let email: String; let password: String; let code: String }
        return try await APIClient.shared.postJSON(
            "/auth/register", body: Body(email: email, password: password, code: code)
        )
    }

    // MARK: - 手机号
    //
    // 与邮箱那套完全平行。号码归一化在服务端做（同一个号可能写成 13800138000、
    // +86 138-0013-8000 等多种形式），客户端原样上传用户输入即可。

    static func requestPhoneRegisterCode(phone: String) async throws {
        struct Body: Encodable { let phone: String }
        let _: RegisterCodeSentResponse = try await APIClient.shared.postJSON(
            "/auth/phone/register/request-code", body: Body(phone: phone)
        )
    }

    static func registerByPhone(phone: String, password: String, code: String) async throws -> AuthTokenResponse {
        struct Body: Encodable { let phone: String; let password: String; let code: String }
        return try await APIClient.shared.postJSON(
            "/auth/phone/register", body: Body(phone: phone, password: password, code: code)
        )
    }

    static func loginByPhone(phone: String, password: String) async throws -> AuthTokenResponse {
        struct Body: Encodable { let phone: String; let password: String }
        return try await APIClient.shared.postJSON(
            "/auth/phone/login", body: Body(phone: phone, password: password)
        )
    }

    static func requestPhonePasswordReset(phone: String) async throws {
        struct Body: Encodable { let phone: String }
        let _: PasswordResetSentResponse = try await APIClient.shared.postJSON(
            "/auth/phone/password-reset/request", body: Body(phone: phone)
        )
    }

    static func confirmPhonePasswordReset(phone: String, code: String, newPassword: String) async throws {
        struct Body: Encodable {
            let phone: String
            let code: String
            let newPassword: String
            enum CodingKeys: String, CodingKey {
                case phone, code
                case newPassword = "new_password"
            }
        }
        let _: PasswordResetDoneResponse = try await APIClient.shared.postJSON(
            "/auth/phone/password-reset/confirm",
            body: Body(phone: phone, code: code, newPassword: newPassword)
        )
    }

    // MARK: - 邮箱

    static func login(email: String, password: String) async throws -> AuthTokenResponse {
        struct Body: Encodable { let email: String; let password: String }
        return try await APIClient.shared.postJSON("/auth/login", body: Body(email: email, password: password))
    }

    static func me() async throws -> UserProfile {
        try await APIClient.shared.get("/auth/me")
    }

    static func changePassword(oldPassword: String, newPassword: String) async throws {
        struct Body: Encodable { let oldPassword: String; let newPassword: String
            enum CodingKeys: String, CodingKey { case oldPassword = "old_password"; case newPassword = "new_password" }
        }
        let _: ChangePasswordResponse = try await APIClient.shared.postJSON(
            "/auth/change-password", body: Body(oldPassword: oldPassword, newPassword: newPassword)
        )
    }

    /// 请求给邮箱发一个找回密码的验证码。
    ///
    /// 后端对「邮箱未注册」也返回成功（防账号枚举），所以这里拿到 200
    /// 不代表该邮箱一定存在，UI 文案要按「如果该邮箱已注册，验证码已发出」来写。
    static func requestPasswordReset(email: String) async throws {
        struct Body: Encodable { let email: String }
        let _: PasswordResetSentResponse = try await APIClient.shared.postJSON(
            "/auth/password-reset/request", body: Body(email: email)
        )
    }

    /// 凭验证码设置新密码。
    static func confirmPasswordReset(email: String, code: String, newPassword: String) async throws {
        struct Body: Encodable {
            let email: String
            let code: String
            let newPassword: String
            enum CodingKeys: String, CodingKey {
                case email, code
                case newPassword = "new_password"
            }
        }
        let _: PasswordResetDoneResponse = try await APIClient.shared.postJSON(
            "/auth/password-reset/confirm",
            body: Body(email: email, code: code, newPassword: newPassword)
        )
    }

    /// 彻底删除账号及全部数据，需带当前密码二次确认。不可恢复。
    ///
    /// 用 POST 而不是 DELETE：带 body 的 DELETE 语义未定义，部分代理会丢掉 body，
    /// 而这里必须把密码传给后端校验。
    static func deleteAccount(password: String) async throws {
        struct Body: Encodable { let password: String }
        let _: DeleteAccountResponse = try await APIClient.shared.postJSON(
            "/auth/delete-account", body: Body(password: password)
        )
    }
}
