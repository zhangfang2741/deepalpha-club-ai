import Foundation
import Testing
@testable import DeepAlphaCore

@MainActor
struct APIClientTests {
    func makeClient(_ mock: MockServer, token: String? = "tok") -> APIClient {
        APIClient(baseURL: URL(string: "https://api.example.com")!,
                  session: mock.session,
                  tokenProvider: { token })
    }

    @Test("GET：带 Authorization 头 + 解析响应")
    func getWithAuth() async throws {
        let mock = MockServer()
        let captured = LockedRequestBox()
        mock.handler = { req in
            captured.set(req)
            let resp = HTTPURLResponse(url: req.url!, statusCode: 200,
                                       httpVersion: nil, headerFields: nil)!
            let body = #"{"run_id":"r1","request_id":"x"}"#
            return (resp, Data(body.utf8))
        }
        struct CreateRunResponse: Decodable { let runId: String
            enum CodingKeys: String, CodingKey { case runId = "run_id" } }

        let client = makeClient(mock)
        let resp: CreateRunResponse = try await client.get("/a")
        #expect(resp.runId == "r1")
        let req = try #require(captured.get())
        #expect(req.value(forHTTPHeaderField: "Authorization") == "Bearer tok")
        #expect(req.url?.absoluteString == "https://api.example.com/a")
    }

    @Test("GET query：参数排序拼接")
    func getQuery() async throws {
        let mock = MockServer()
        let captured = LockedRequestBox()
        mock.handler = { req in
            captured.set(req)
            return (HTTPURLResponse(url: req.url!, statusCode: 200,
                                    httpVersion: nil, headerFields: nil)!,
                     Data(#"{"runs":[]}"#.utf8))
        }
        let client = makeClient(mock)
        let _: RunListResponse = try await client.get("/runs", query: ["limit": "50", "offset": "0"])
        let req = try #require(captured.get())
        #expect(req.url?.query == "limit=50&offset=0")
    }

    @Test("POST JSON：Content-Type 与 body")
    func postJson() async throws {
        let mock = MockServer()
        let captured = LockedRequestBox()
        mock.handler = { req in
            captured.set(req)
            return (HTTPURLResponse(url: req.url!, statusCode: 200,
                                    httpVersion: nil, headerFields: nil)!,
                     Data(#"{"accepted":true}"#.utf8))
        }
        struct ControlResponse: Decodable { let accepted: Bool }
        struct Body: Encodable { let action: String; let text: String? }

        let client = makeClient(mock, token: nil)
        let resp: ControlResponse = try await client.post(
            "/api/v1/trading-desk/runs/r1/control", json: Body(action: "pause", text: nil))
        #expect(resp.accepted)
        let req = try #require(captured.get())
        #expect(req.httpMethod == "POST")
        #expect(req.value(forHTTPHeaderField: "Content-Type") == "application/json")
        let body = try #require(req.httpBody ?? req.httpBodyStreamData)
        #expect(String(data: body, encoding: .utf8) == #"{"action":"pause"}"#)
        #expect(req.value(forHTTPHeaderField: "Authorization") == nil)
    }

    @Test("POST form-urlencoded（登录）")
    func postForm() async throws {
        let mock = MockServer()
        let captured = LockedRequestBox()
        mock.handler = { req in
            captured.set(req)
            return (HTTPURLResponse(url: req.url!, statusCode: 200,
                                    httpVersion: nil, headerFields: nil)!,
                     Data(#"{"access_token":"jwt","token_type":"bearer"}"#.utf8))
        }
        struct LoginResponse: Decodable { let accessToken: String
            enum CodingKeys: String, CodingKey { case accessToken = "access_token" } }

        let client = makeClient(mock, token: nil)
        let resp: LoginResponse = try await client.postForm(
            "/api/v1/auth/login",
            fields: ["email": "a@b.c", "password": "p w+d", "grant_type": "password"])
        #expect(resp.accessToken == "jwt")
        let req = try #require(captured.get())
        #expect(req.value(forHTTPHeaderField: "Content-Type")
                == "application/x-www-form-urlencoded")
        let body = try #require(req.httpBody ?? req.httpBodyStreamData)
        #expect(String(data: body, encoding: .utf8)
                == "email=a%40b.c&grant_type=password&password=p%20w%2Bd")
    }

    @Test("401 → .unauthorized；404 → .notFound；detail 消息透出")
    func errorMapping() async {
        let mock = MockServer()
        mock.handler = { req in
            let code = Int(req.url!.lastPathComponent) ?? 500
            let resp = HTTPURLResponse(url: req.url!, statusCode: code,
                                       httpVersion: nil, headerFields: nil)!
            let body = Data(#"{"detail":"运行不存在"}"#.utf8)
            return (resp, body)
        }
        struct Empty: Decodable {}
        let client = makeClient(mock)
        do {
            let _: Empty = try await client.get("/e/401")
            Issue.record("应抛 unauthorized")
        } catch let e as APIError {
            #expect(e.isUnauthorized)
            // 401 的 detail 是字符串时也应透出，而不是被固定文案盖掉
            #expect(e.message == "运行不存在")
        } catch {
            Issue.record("错误类型不对：\(error)")
        }
        do {
            let _: Empty = try await client.get("/e/404")
            Issue.record("应抛 notFound")
        } catch let e as APIError {
            #expect(e == .notFound)
            #expect(e.message == "资源不存在") // 404 固定文案，不透出 detail
        } catch {
            Issue.record("错误类型不对：\(error)")
        }
        await #expect(throws: APIError.self) {
            let _: Empty = try await client.get("/e/500")
        }
    }

    @Test("401 的 dict detail：登录接口的「账号或密码错误」要原样透出")
    func unauthorizedDictDetail() async {
        let mock = MockServer()
        mock.handler = { req in
            let resp = HTTPURLResponse(url: req.url!, statusCode: 401,
                                       httpVersion: nil, headerFields: nil)!
            // /auth/login/account 的真实响应形状
            let body = #"{"detail":{"message":"账号或密码错误","code":"INVALID_CREDENTIALS"}}"#
            return (resp, Data(body.utf8))
        }
        struct Empty: Decodable {}
        let client = makeClient(mock)
        do {
            let _: Empty = try await client.get("/auth/login/account")
            Issue.record("应抛 unauthorized")
        } catch let e as APIError {
            #expect(e.isUnauthorized)
            #expect(e.message == "账号或密码错误")
        } catch {
            Issue.record("错误类型不对：\(error)")
        }
    }

    @Test("401 无 body：回落到通用过期文案")
    func unauthorizedNoBody() async {
        let mock = MockServer()
        mock.handler = { req in
            (HTTPURLResponse(url: req.url!, statusCode: 401,
                             httpVersion: nil, headerFields: nil)!, Data())
        }
        struct Empty: Decodable {}
        let client = makeClient(mock)
        do {
            let _: Empty = try await client.get("/x")
            Issue.record("应抛 unauthorized")
        } catch let e as APIError {
            #expect(e.isUnauthorized)
            #expect(e.message == "登录已过期，请重新登录")
        } catch {
            Issue.record("错误类型不对：\(error)")
        }
    }

    @Test("连接层错误 → .network")
    func networkError() async {
        let mock = MockServer()
        struct Boom: Error {}
        mock.handler = { _ in throw Boom() }
        struct Empty: Decodable {}
        let client = makeClient(mock)
        await #expect(throws: APIError.network) {
            let _: Empty = try await client.get("/x")
        }
    }
}
