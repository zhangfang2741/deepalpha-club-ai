import Foundation
import Testing
@testable import Core

@MainActor
struct AuthServiceTests {
    func makeClient() -> APIClient {
        APIClient(baseURL: URL(string: "https://api.example.com")!,
                  session: MockURLProtocol.makeSession(),
                  tokenProvider: { nil })
    }

    @Test("登录成功：form 字段正确 + 返回 token", .resetMock)
    func loginOk() async throws {
        let captured = LockedRequestBox()
        MockURLProtocol.handler = { req in
            captured.set(req)
            let resp = HTTPURLResponse(url: req.url!, statusCode: 200,
                                       httpVersion: nil, headerFields: nil)!
            return (resp, Data(#"{"access_token":"jwt-1","token_type":"bearer","expires_at":"2026-12-01T00:00:00Z","request_id":"r"}"#.utf8))
        }
        let service = AuthService(client: makeClient())
        let token = try await service.login(email: "a@b.c", password: "secret8")
        #expect(token == "jwt-1")
        let req = try #require(captured.get())
        #expect(req.url?.path == "/api/v1/auth/login")
        let body = try #require(req.httpBody ?? req.httpBodyStreamData)
        #expect(String(data: body, encoding: .utf8)?.contains("email=a%40b.c") == true)
        #expect(String(data: body, encoding: .utf8)?.contains("grant_type=password") == true)
    }

    @Test("登录失败 401 → 抛 APIError.unauthorized", .resetMock)
    func loginFail() async {
        MockURLProtocol.handler = { req in
            let resp = HTTPURLResponse(url: req.url!, statusCode: 401,
                                       httpVersion: nil, headerFields: nil)!
            return (resp, Data(#"{"detail":"邮箱或密码错误"}"#.utf8))
        }
        let service = AuthService(client: makeClient())
        do {
            _ = try await service.login(email: "a@b.c", password: "wrong!!")
            Issue.record("应抛错")
        } catch let e as APIError {
            #expect(e == .unauthorized)
        } catch {
            Issue.record("错误类型不对：\(error)")
        }
    }

    @Test("InMemoryKeychain 存取删")
    func inMemoryKeychain() {
        let k = InMemoryKeychain()
        #expect(k.loadToken() == nil)
        try? k.saveToken("t1")
        #expect(k.loadToken() == "t1")
        k.deleteToken()
        #expect(k.loadToken() == nil)
    }
}
