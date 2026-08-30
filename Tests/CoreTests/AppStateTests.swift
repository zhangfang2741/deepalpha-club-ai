import Foundation
import Testing
@testable import Core

struct MockAuth: AuthServiceProtocol, Sendable {
    var result: Result<String, Error>
    func login(email: String, password: String) async throws -> String {
        switch result {
        case .success(let t): return t
        case .failure(let e): throw e
        }
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
                           auth: MockAuth(result: .failure(APIError.unauthorized)))
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
