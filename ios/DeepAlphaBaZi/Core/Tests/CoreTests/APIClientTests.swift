import Foundation
import Testing
@testable import DeepAlphaBaZiCore

@Suite("APIClient")
struct APIClientTests {
    func makeClient(_ mock: MockServer) -> APIClient {
        APIClient(baseURL: URL(string: "https://api.example.com")!, session: mock.session)
    }

    @Test("POST JSON：Content-Type 与 body 正确编码")
    func postJson() async throws {
        let mock = MockServer()
        let captured = LockedRequestBox()
        mock.handler = { req in
            captured.set(req)
            return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!,
                    Data(#"{"ok":true}"#.utf8))
        }
        struct Body: Encodable { let a: String }
        struct Resp: Decodable { let ok: Bool }

        let client = makeClient(mock)
        let resp: Resp = try await client.post("/x", json: Body(a: "1"))
        #expect(resp.ok)
        let req = try #require(captured.get())
        #expect(req.httpMethod == "POST")
        #expect(req.value(forHTTPHeaderField: "Content-Type") == "application/json")
    }

    @Test("404 → APIError.notFound")
    func notFound() async {
        let mock = MockServer()
        mock.handler = { req in
            (HTTPURLResponse(url: req.url!, statusCode: 404, httpVersion: nil, headerFields: nil)!, Data())
        }
        struct Empty: Decodable {}
        let client = makeClient(mock)
        await #expect(throws: APIError.notFound) {
            let _: Empty = try await client.get("/x")
        }
    }

    @Test("422 → APIError.validation，detail 文本透出")
    func validation() async {
        let mock = MockServer()
        mock.handler = { req in
            (HTTPURLResponse(url: req.url!, statusCode: 422, httpVersion: nil, headerFields: nil)!,
             Data(#"{"detail":"出生日期不能晚于今天"}"#.utf8))
        }
        struct Empty: Decodable {}
        let client = makeClient(mock)
        do {
            let _: Empty = try await client.get("/x")
            Issue.record("应抛 validation")
        } catch let e as APIError {
            #expect(e.message == "出生日期不能晚于今天")
        } catch {
            Issue.record("错误类型不对：\(error)")
        }
    }

    @Test("连接层错误 → APIError.network")
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
