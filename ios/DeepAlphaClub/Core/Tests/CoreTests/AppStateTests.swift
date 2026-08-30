import Foundation
import Testing
@testable import DeepAlphaCore

/// 认证替身：token 类接口返回 result，发码/重置类返回 voidResult。
struct MockAuth: AuthServiceProtocol, Sendable {
    var result: Result<String, Error>
    var voidResult: Result<Void, Error> = .success(())

    private func token() throws -> String {
        switch result {
        case .success(let t): return t
        case .failure(let e): throw e
        }
    }
    private func void() throws {
        if case .failure(let e) = voidResult { throw e }
    }

    func login(email: String, password: String) async throws -> String { try token() }
    func login(account: String, password: String) async throws -> String { try token() }
    func register(account: String, channel: AccountChannel, code: String,
                  password: String, username: String?) async throws -> String { try token() }
    func requestRegisterCode(account: String, channel: AccountChannel) async throws { try void() }
    func requestPasswordResetCode(account: String, channel: AccountChannel) async throws { try void() }
    func confirmPasswordReset(account: String, channel: AccountChannel,
                              code: String, newPassword: String) async throws { try void() }
}

/// 写入永远失败的 Keychain：模拟器缺 entitlement 时 SecItemAdd 返回 -34018，
/// 真机磁盘异常也可能失败——这条路径必须被覆盖。
struct FailingKeychain: KeychainStoring {
    struct WriteFailed: Error {}
    func saveToken(_ token: String) throws { throw WriteFailed() }
    func loadToken() -> String? { nil }
    func deleteToken() {}
}

/// 记录调用参数的替身：验证 AppState 是否原样把入参转发给 service。
final class RecordingAuth: AuthServiceProtocol, @unchecked Sendable {
    struct Call: Equatable {
        var method: String
        var account: String
        var channel: AccountChannel?
        var code: String?
        var password: String?
        var username: String?
    }

    private let lock = NSLock()
    private var _calls: [Call] = []
    var calls: [Call] { lock.withLock { _calls } }
    private func record(_ c: Call) { lock.withLock { _calls.append(c) } }

    func login(email: String, password: String) async throws -> String {
        record(.init(method: "login(email:)", account: email, password: password))
        return "jwt"
    }
    func login(account: String, password: String) async throws -> String {
        record(.init(method: "login(account:)", account: account, password: password))
        return "jwt"
    }
    func register(account: String, channel: AccountChannel, code: String,
                  password: String, username: String?) async throws -> String {
        record(.init(method: "register", account: account, channel: channel,
                     code: code, password: password, username: username))
        return "jwt-reg"
    }
    func requestRegisterCode(account: String, channel: AccountChannel) async throws {
        record(.init(method: "requestRegisterCode", account: account, channel: channel))
    }
    func requestPasswordResetCode(account: String, channel: AccountChannel) async throws {
        record(.init(method: "requestPasswordResetCode", account: account, channel: channel))
    }
    func confirmPasswordReset(account: String, channel: AccountChannel,
                              code: String, newPassword: String) async throws {
        record(.init(method: "confirmPasswordReset", account: account, channel: channel,
                     code: code, password: newPassword))
    }
}

@MainActor
@Suite("AppState")
struct AppStateTests {
    @Test("restore：Keychain 有 token → 已登录")
    func restoreWithToken() {
        let keychain = InMemoryKeychain()
        try? keychain.saveToken("jwt")
        let app = AppState(keychain: keychain, auth: MockAuth(result: .success("x")))
        app.restoreFromKeychain()
        #expect(app.isLoggedIn)
        #expect(app.token == "jwt")
    }

    @Test("restore：无 token → 未登录")
    func restoreWithoutToken() {
        let app = AppState(keychain: InMemoryKeychain(), auth: MockAuth(result: .success("x")))
        app.restoreFromKeychain()
        #expect(!app.isLoggedIn)
    }

    @Test("login 成功：token 入 Keychain")
    func loginSuccess() async {
        let keychain = InMemoryKeychain()
        let app = AppState(keychain: keychain, auth: MockAuth(result: .success("jwt-2")))
        let ok = await app.login(email: "a@b.c", password: "secret8")
        #expect(ok)
        #expect(app.isLoggedIn)
        #expect(keychain.loadToken() == "jwt-2")
        #expect(app.authError == nil)
    }

    @Test("login 失败：错误展示，token 不落盘")
    func loginFailure() async {
        let keychain = InMemoryKeychain()
        let app = AppState(keychain: keychain,
                           auth: MockAuth(result: .failure(APIError.unauthorized(nil))))
        let ok = await app.login(email: "a@b.c", password: "wrong!!")
        #expect(!ok)
        #expect(!app.isLoggedIn)
        #expect(app.authError == "登录已过期，请重新登录")
        #expect(keychain.loadToken() == nil)
    }

    @Test("login 空输入：本地校验错误")
    func loginEmpty() async {
        let app = AppState(keychain: InMemoryKeychain(), auth: MockAuth(result: .success("x")))
        let ok = await app.login(email: "", password: "")
        #expect(!ok)
        #expect(app.authError == "请输入邮箱和密码")
    }

    @Test("handleUnauthorized：清 token → 未登录（回登录页）")
    func handleUnauthorized() {
        let keychain = InMemoryKeychain()
        try? keychain.saveToken("jwt")
        let app = AppState(keychain: keychain, auth: MockAuth(result: .success("x")))
        app.restoreFromKeychain()
        app.handleUnauthorized()
        #expect(!app.isLoggedIn)
        #expect(keychain.loadToken() == nil)
    }

    @Test("Keychain 写失败不该挡住登录：token 已到手，本次会话照常可用")
    func loginSucceedsWhenKeychainWriteFails() async {
        let app = AppState(keychain: FailingKeychain(), auth: MockAuth(result: .success("jwt-x")))

        let ok = await app.login(account: "a@b.c", password: "secret8")

        #expect(ok)
        #expect(app.isLoggedIn)
        #expect(app.token == "jwt-x")
        #expect(app.authError == nil)                  // 不是错误，不该拦人
        #expect(app.persistenceWarning != nil)         // 但要告知下次得重登
    }

    // MARK: - 双通道登录 / 注册 / 找回密码

    @Test("统一登录：转发 account 原样给 service，token 落 Keychain")
    func loginByAccount() async {
        let keychain = InMemoryKeychain()
        let auth = RecordingAuth()
        let app = AppState(keychain: keychain, auth: auth)

        let ok = await app.login(account: "13800138000", password: "secret8")

        #expect(ok)
        #expect(app.isLoggedIn)
        #expect(keychain.loadToken() == "jwt")
        #expect(auth.calls == [.init(method: "login(account:)", account: "13800138000",
                                     password: "secret8")])
    }

    @Test("统一登录空输入：不发请求")
    func loginByAccountEmpty() async {
        let auth = RecordingAuth()
        let app = AppState(keychain: InMemoryKeychain(), auth: auth)
        let ok = await app.login(account: "", password: "")
        #expect(!ok)
        #expect(app.authError == "请输入账号和密码")
        #expect(auth.calls.isEmpty)
    }

    @Test("注册成功：直接登录（token 落 Keychain）+ 参数原样转发")
    func register() async {
        let keychain = InMemoryKeychain()
        let auth = RecordingAuth()
        let app = AppState(keychain: keychain, auth: auth)

        let ok = await app.register(account: "a@b.c", channel: .email, code: "123456",
                                    password: "secret8", username: "u")

        #expect(ok)
        #expect(app.isLoggedIn)
        #expect(keychain.loadToken() == "jwt-reg")
        #expect(auth.calls.first == .init(method: "register", account: "a@b.c",
                                          channel: .email, code: "123456",
                                          password: "secret8", username: "u"))
    }

    @Test("发注册码：成功返回 true（界面据此启动倒计时）")
    func requestRegisterCode() async {
        let auth = RecordingAuth()
        let app = AppState(keychain: InMemoryKeychain(), auth: auth)

        let sent = await app.requestRegisterCode(account: "13800138000", channel: .phone)

        #expect(sent)
        #expect(auth.calls == [.init(method: "requestRegisterCode",
                                     account: "13800138000", channel: .phone)])
    }

    @Test("发注册码失败：返回 false + 错误文案，不启动倒计时")
    func requestRegisterCodeFailure() async {
        let app = AppState(
            keychain: InMemoryKeychain(),
            auth: MockAuth(result: .success("x"),
                           voidResult: .failure(APIError.server(400, "该邮箱已被注册，请直接登录"))))

        let sent = await app.requestRegisterCode(account: "a@b.c", channel: .email)

        #expect(!sent)
        #expect(app.authError == "该邮箱已被注册，请直接登录")
    }

    @Test("重置密码：成功返回 true，但不自动登录（要用新密码重登）")
    func resetPassword() async {
        let keychain = InMemoryKeychain()
        let auth = RecordingAuth()
        let app = AppState(keychain: keychain, auth: auth)

        let ok = await app.resetPassword(account: "a@b.c", channel: .email,
                                         code: "123456", newPassword: "newpass8")

        #expect(ok)
        #expect(!app.isLoggedIn)              // 重置密码不等于登录
        #expect(keychain.loadToken() == nil)
        #expect(auth.calls.first?.method == "confirmPasswordReset")
    }

    @Test("logout：清 Keychain")
    func logout() {
        let keychain = InMemoryKeychain()
        try? keychain.saveToken("jwt")
        let app = AppState(keychain: keychain, auth: MockAuth(result: .success("x")))
        app.restoreFromKeychain()
        app.logout()
        #expect(!app.isLoggedIn)
    }
}
