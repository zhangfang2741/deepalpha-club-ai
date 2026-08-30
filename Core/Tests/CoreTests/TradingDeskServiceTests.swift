import Foundation
import Testing
@testable import DeepAlphaCore

@Suite("TradingDeskService")
struct TradingDeskServiceTests {
    func makeService(_ mock: MockServer) -> TradingDeskService {
        TradingDeskService(
            api: APIClient(baseURL: URL(string: "https://api.example.com")!,
                           session: mock.session, tokenProvider: { "t" }),
            sse: SSEClient(baseURL: URL(string: "https://api.example.com")!,
                           session: mock.session, tokenProvider: { "t" }))
    }

    @Test("createRun：POST /runs + ticker JSON body")
    func createRun() async throws {
        let mock = MockServer()
        let captured = LockedRequestBox()
        mock.handler = { req in
            captured.set(req)
            return (HTTPURLResponse(url: req.url!, statusCode: 200,
                                    httpVersion: nil, headerFields: nil)!,
                    Data(#"{"run_id":"run-1"}"#.utf8))
        }
        let runId = try await makeService(mock).createRun(ticker: "NVDA")
        #expect(runId == "run-1")
        let req = try #require(captured.get())
        #expect(req.url?.path == "/api/v1/trading-desk/runs")
        #expect(req.httpMethod == "POST")
        let body = try #require(req.httpBody ?? req.httpBodyStreamData)
        #expect(String(data: body, encoding: .utf8) == #"{"ticker":"NVDA"}"#)
    }

    @Test("controlRun：action + text")
    func controlRun() async throws {
        let mock = MockServer()
        let captured = LockedRequestBox()
        mock.handler = { req in
            captured.set(req)
            return (HTTPURLResponse(url: req.url!, statusCode: 200,
                                    httpVersion: nil, headerFields: nil)!,
                    Data(#"{"accepted":true}"#.utf8))
        }
        try await makeService(mock).control(runId: "run-1", action: .inject, text: "注意风险")
        let req = try #require(captured.get())
        #expect(req.url?.path == "/api/v1/trading-desk/runs/run-1/control")
        let body = try #require(req.httpBody ?? req.httpBodyStreamData)
        // JSON 键顺序无语义，解析后比较
        let decoded = try #require(try JSONSerialization.jsonObject(with: body) as? [String: String])
        #expect(decoded == ["action": "inject", "text": "注意风险"])
    }

    @Test("listRuns：query 参数 ticker/limit/offset")
    func listRuns() async throws {
        let mock = MockServer()
        let captured = LockedRequestBox()
        mock.handler = { req in
            captured.set(req)
            return (HTTPURLResponse(url: req.url!, statusCode: 200,
                                    httpVersion: nil, headerFields: nil)!,
                    Data(#"{"runs":[]}"#.utf8))
        }
        let resp: RunListResponse = try await makeService(mock)
            .listRuns(ticker: "nvda", limit: 50, offset: 10)
        #expect(resp.runs.isEmpty)
        let req = try #require(captured.get())
        #expect(req.url?.path == "/api/v1/trading-desk/runs")
        #expect(req.url?.query?.contains("ticker=NVDA") == true)
        #expect(req.url?.query?.contains("limit=50") == true)
        #expect(req.url?.query?.contains("offset=10") == true)
    }

    @Test("getRun：详情路径")
    func getRun() async throws {
        let mock = MockServer()
        let captured = LockedRequestBox()
        mock.handler = { req in
            captured.set(req)
            return (HTTPURLResponse(url: req.url!, statusCode: 200,
                                    httpVersion: nil, headerFields: nil)!,
                    Data("""
                    {"run_id":"run-1","ticker":"NVDA","trade_date":"2026-08-30","engine":"e",
                     "status":"completed","duration_ms":1,
                     "created_at":"2026-08-30T10:00:00+00:00","finished_at":null,
                     "verdict":null,"signals":[],"turns":[]}
                    """.utf8))
        }
        let detail = try await makeService(mock).getRun(runId: "run-1")
        #expect(detail.runId == "run-1")
        let req = try #require(captured.get())
        #expect(req.url?.path == "/api/v1/trading-desk/runs/run-1")
    }

    @Test("stream 委托 SSEClient（URL 路径正确）")
    func streamDelegation() async throws {
        let mock = MockServer()
        let captured = LockedRequestBox()
        mock.handler = { req in
            captured.set(req)
            return (HTTPURLResponse(url: req.url!, statusCode: 200,
                                    httpVersion: nil, headerFields: nil)!,
                    Data("data: {\"type\":\"run.finished\",\"run_id\":\"run-1\",\"seq\":1,\"ts\":0,\"data\":{}}\n\n".utf8))
        }
        var count = 0
        for try await _ in makeService(mock).stream(runId: "run-1", lastEventId: nil) { count += 1 }
        #expect(count == 1)
        #expect(captured.get()?.url?.path == "/api/v1/trading-desk/runs/run-1/stream")
    }
}
