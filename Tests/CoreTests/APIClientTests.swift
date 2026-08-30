import Foundation
import Testing
@testable import Core

@MainActor
struct APIClientTests {
    func makeClient(token: String? = "tok") -> APIClient {
        APIClient(baseURL: URL(string: "https://api.example.com")!,
                  session: MockURLProtocol.makeSession(),
                  tokenProvider: { token })
    }

    @Test("GET：带 Authorization 头 + 解析响应", .resetMock)
    func getWithAuth() async throws {
        let captured = LockedRequestBox()
        MockURLProtocol.handler = { req in
            captured.set(req)
            let resp = HTTPURLResponse(url: req.url!, statusCode: 200,
                                       httpVersion: nil, headerFields: nil)!
            let body = #"{"run_id":"r1","request_id":"x"}"#
            return (resp, Data(body.utf8))
        }
        struct CreateRunResponse: Decodable { let runId: String
            enum CodingKeys: String, CodingKey { case runId = "run_id" } }

        let client = makeClient()
        let resp: CreateRunResponse = try await client.get("/a")
        #expect(resp.runId == "r1")
        let req = try #require(captured.get())
        #expect(req.value(forHTTPHeaderField: "Authorization") == "Bearer tok")
        #expect(req.url?.absoluteString == "https://api.example.com/a")
    }

    @Test("GET query：参数排序拼接", .resetMock)
    func getQuery() async throws {
        let captured = LockedRequestBox()
        MockURLProtocol.handler = { req in
            captured.set(req)
            return (HTTPURLResponse(url: req.url!, statusCode: 200,
                                    httpVersion: nil, headerFields: nil)!,
                     Data(#"{"runs":[]}"#.utf8))
        }
        let client = makeClient()
        let _: RunListResponse = try await client.get("/runs", query: ["limit": "50", "offset": "0"])
        let req = try #require(captured.get())
        #expect(req.url?.query == "limit=50&offset=0")
    }

    @Test("POST JSON：Content-Type 与 body", .resetMock)
    func postJson() async throws {
        let captured = LockedRequestBox()
        MockURLProtocol.handler = { req in
            captured.set(req)
            return (HTTPURLResponse(url: req.url!, statusCode: 200,
                                    httpVersion: nil, headerFields: nil)!,
                     Data(#"{"accepted":true}"#.utf8))
        }
        struct ControlResponse: Decodable { let accepted: Bool }
        struct Body: Encodable { let action: String; let text: String? }

        let client = makeClient(token: nil)
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

    @Test("POST form-urlencoded（登录）", .resetMock)
    func postForm() async throws {
        let captured = LockedRequestBox()
        MockURLProtocol.handler = { req in
            captured.set(req)
            return (HTTPURLResponse(url: req.url!, statusCode: 200,
                                    httpVersion: nil, headerFields: nil)!,
                     Data(#"{"access_token":"jwt","token_type":"bearer"}"#.utf8))
        }
        struct LoginResponse: Decodable { let accessToken: String
            enum CodingKeys: String, CodingKey { case accessToken = "access_token" } }

        let client = makeClient(token: nil)
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

    @Test("401 → .unauthorized；404 → .notFound；detail 消息透出", .resetMock)
    func errorMapping() async {
        MockURLProtocol.handler = { req in
            let code = Int(req.url!.lastPathComponent) ?? 500
            let resp = HTTPURLResponse(url: req.url!, statusCode: code,
                                       httpVersion: nil, headerFields: nil)!
            let body = Data(#"{"detail":"运行不存在"}"#.utf8)
            return (resp, body)
        }
        struct Empty: Decodable {}
        let client = makeClient()
        await #expect(throws: APIError.unauthorized) {
            let _: Empty = try await client.get("/e/401")
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

    @Test("连接层错误 → .network", .resetMock)
    func networkError() async {
        struct Boom: Error {}
        MockURLProtocol.handler = { _ in throw Boom() }
        struct Empty: Decodable {}
        let client = makeClient()
        await #expect(throws: APIError.network) {
            let _: Empty = try await client.get("/x")
        }
    }
}
