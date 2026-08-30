import Foundation
import Testing
@testable import DeepAlphaCore

@MainActor
struct AuthServiceTests {
    func makeClient(_ mock: MockServer) -> APIClient {
        APIClient(baseURL: URL(string: "https://api.example.com")!,
                  session: mock.session,
                  tokenProvider: { nil })
    }

    @Test("登录成功：form 字段正确 + 返回 token")
    func loginOk() async throws {
        let mock = MockServer()
        let captured = LockedRequestBox()
        mock.handler = { req in
            captured.set(req)
            let resp = HTTPURLResponse(url: req.url!, statusCode: 200,
                                       httpVersion: nil, headerFields: nil)!
            return (resp, Data(#"{"access_token":"jwt-1","token_type":"bearer","expires_at":"2026-12-01T00:00:00Z","request_id":"r"}"#.utf8))
        }
        let service = AuthService(client: makeClient(mock))
        let token = try await service.login(email: "a@b.c", password: "secret8")
        #expect(token == "jwt-1")
        let req = try #require(captured.get())
        #expect(req.url?.path == "/api/v1/auth/login")
        let body = try #require(req.httpBody ?? req.httpBodyStreamData)
        #expect(String(data: body, encoding: .utf8)?.contains("email=a%40b.c") == true)
        #expect(String(data: body, encoding: .utf8)?.contains("grant_type=password") == true)
    }

    @Test("登录失败 401 → 抛 APIError.unauthorized")
    func loginFail() async {
        let mock = MockServer()
        mock.handler = { req in
            let resp = HTTPURLResponse(url: req.url!, statusCode: 401,
                                       httpVersion: nil, headerFields: nil)!
            return (resp, Data(#"{"detail":"邮箱或密码错误"}"#.utf8))
        }
        let service = AuthService(client: makeClient(mock))
        do {
            _ = try await service.login(email: "a@b.c", password: "wrong!!")
            Issue.record("应抛错")
        } catch let e as APIError {
            #expect(e.isUnauthorized)
        } catch {
            Issue.record("错误类型不对：\(error)")
        }
    }

    // MARK: - 双通道登录 / 注册 / 找回密码

    /// 造一个只回 200 + 指定 body 的假服务器，并捕获请求。
    private func stub(_ mock: MockServer, _ box: LockedRequestBox, json: String) {
        mock.handler = { req in
            box.set(req)
            return (HTTPURLResponse(url: req.url!, statusCode: 200,
                                    httpVersion: nil, headerFields: nil)!,
                    Data(json.utf8))
        }
    }

    private func bodyJSON(_ req: URLRequest) throws -> [String: String] {
        let data = try #require(req.httpBody ?? req.httpBodyStreamData)
        let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return (obj ?? [:]).compactMapValues { $0 as? String }
    }

    @Test("统一登录：POST /auth/login/account，account 由服务端判别手机/邮箱")
    func loginByAccount() async throws {
        let mock = MockServer(); let box = LockedRequestBox()
        stub(mock, box, json: #"{"access_token":"jwt-acc","token_type":"bearer"}"#)

        let service = AuthService(client: makeClient(mock))
        let token = try await service.login(account: "13800138000", password: "secret8")

        #expect(token == "jwt-acc")
        let req = try #require(box.get())
        #expect(req.url?.path == "/api/v1/auth/login/account")
        #expect(req.httpMethod == "POST")
        #expect(try bodyJSON(req) == ["account": "13800138000", "password": "secret8"])
    }

    @Test("注册发码：邮箱走 /register/request-code，手机走 /phone/register/request-code")
    func requestRegisterCode() async throws {
        let mockEmail = MockServer(); let boxEmail = LockedRequestBox()
        stub(mockEmail, boxEmail, json: #"{"sent":true}"#)
        let emailService = AuthService(client: makeClient(mockEmail))
        try await emailService.requestRegisterCode(account: "a@b.c", channel: .email)
        let emailReq = try #require(boxEmail.get())
        #expect(emailReq.url?.path == "/api/v1/auth/register/request-code")
        #expect(try bodyJSON(emailReq) == ["email": "a@b.c"])

        let mockPhone = MockServer(); let boxPhone = LockedRequestBox()
        stub(mockPhone, boxPhone, json: #"{"sent":true}"#)
        let phoneService = AuthService(client: makeClient(mockPhone))
        try await phoneService.requestRegisterCode(account: "13800138000", channel: .phone)
        let phoneReq = try #require(boxPhone.get())
        #expect(phoneReq.url?.path == "/api/v1/auth/phone/register/request-code")
        #expect(try bodyJSON(phoneReq) == ["phone": "13800138000"])
    }

    @Test("注册：邮箱通道 /register/verify，返回嵌套 token")
    func registerByEmail() async throws {
        let mock = MockServer(); let box = LockedRequestBox()
        stub(mock, box, json: #"""
        {"id":7,"email":"a@b.c","phone":null,"username":"u",
         "token":{"access_token":"jwt-reg","token_type":"bearer"}}
        """#)
        let service = AuthService(client: makeClient(mock))
        let token = try await service.register(
            account: "a@b.c", channel: .email, code: "123456",
            password: "secret8", username: "u")

        #expect(token == "jwt-reg")
        let req = try #require(box.get())
        #expect(req.url?.path == "/api/v1/auth/register/verify")
        #expect(try bodyJSON(req) == ["email": "a@b.c", "code": "123456",
                                      "password": "secret8", "username": "u"])
    }

    @Test("注册：手机通道 /phone/register；username 为空时不发该字段")
    func registerByPhone() async throws {
        let mock = MockServer(); let box = LockedRequestBox()
        stub(mock, box, json: #"""
        {"id":8,"email":null,"phone":"+8613800138000","username":null,
         "token":{"access_token":"jwt-p","token_type":"bearer"}}
        """#)
        let service = AuthService(client: makeClient(mock))
        let token = try await service.register(
            account: "13800138000", channel: .phone, code: "654321",
            password: "secret8", username: nil)

        #expect(token == "jwt-p")
        let req = try #require(box.get())
        #expect(req.url?.path == "/api/v1/auth/phone/register")
        let fields = try bodyJSON(req)
        #expect(fields["phone"] == "13800138000")
        #expect(fields["code"] == "654321")
        #expect(fields["username"] == nil)   // 空用户名不占位
    }

    @Test("找回密码发码：双通道路径正确")
    func requestPasswordResetCode() async throws {
        let mockEmail = MockServer(); let boxEmail = LockedRequestBox()
        stub(mockEmail, boxEmail, json: #"{"sent":true}"#)
        try await AuthService(client: makeClient(mockEmail))
            .requestPasswordResetCode(account: "a@b.c", channel: .email)
        #expect(try #require(boxEmail.get()).url?.path == "/api/v1/auth/password-reset/request")

        let mockPhone = MockServer(); let boxPhone = LockedRequestBox()
        stub(mockPhone, boxPhone, json: #"{"sent":true}"#)
        try await AuthService(client: makeClient(mockPhone))
            .requestPasswordResetCode(account: "13800138000", channel: .phone)
        #expect(try #require(boxPhone.get()).url?.path
                == "/api/v1/auth/phone/password-reset/request")
    }

    @Test("重置密码：new_password 字段名要与后端一致")
    func confirmPasswordReset() async throws {
        let mock = MockServer(); let box = LockedRequestBox()
        stub(mock, box, json: #"{"reset":true}"#)
        try await AuthService(client: makeClient(mock)).confirmPasswordReset(
            account: "a@b.c", channel: .email, code: "123456", newPassword: "newpass8")

        let req = try #require(box.get())
        #expect(req.url?.path == "/api/v1/auth/password-reset/confirm")
        #expect(try bodyJSON(req) == ["email": "a@b.c", "code": "123456",
                                      "new_password": "newpass8"])
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
