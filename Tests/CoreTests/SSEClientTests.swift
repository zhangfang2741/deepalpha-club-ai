import Foundation
import Testing
@testable import Core

@Suite("SSEClient")
struct SSEClientTests {
    func makeClient(token: String? = "tok") -> SSEClient {
        SSEClient(baseURL: URL(string: "https://api.example.com")!,
                  session: MockURLProtocol.makeSession(),
                  tokenProvider: { token })
    }

    func httpOK(_ url: URL?) -> HTTPURLResponse {
        HTTPURLResponse(url: url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
    }

    @Test("订阅：请求头正确（Bearer / Last-Event-ID / Accept）+ 帧序列产出", .resetMock)
    func streamHeadersAndFrames() async throws {
        let captured = LockedRequestBox()
        let body = "id: 1-0\ndata: {\"type\":\"run.started\",\"run_id\":\"r1\",\"seq\":1,\"ts\":0,\"data\":{}}\n\n"
            + ":\n\n"
            + "data: 坏 JSON\n\n"
            + "id: 1-1\ndata: {\"type\":\"run.paused\",\"run_id\":\"r1\",\"seq\":2,\"ts\":0,\"data\":{}}\n\n"
        MockURLProtocol.handler = { req in
            captured.set(req)
            return (httpOK(req.url), Data(body.utf8))
        }

        let client = makeClient()
        var frames: [SseFrame] = []
        for try await frame in client.stream(runId: "r1", lastEventId: "1-9") {
            frames.append(frame)
        }
        #expect(frames.count == 2)
        if frames.count == 2 { #expect(frames[0].id == "1-0") }
        if frames.count == 2 { #expect(frames[1].event.type == .runPaused) }
        let req = try #require(captured.get())
        #expect(req.url?.absoluteString == "https://api.example.com/api/v1/trading-desk/runs/r1/stream")
        #expect(req.value(forHTTPHeaderField: "Authorization") == "Bearer tok")
        #expect(req.value(forHTTPHeaderField: "Last-Event-ID") == "1-9")
        #expect(req.value(forHTTPHeaderField: "Accept") == "text/event-stream")
    }

    @Test("无 lastEventId 时不发 Last-Event-ID 头", .resetMock)
    func noLastEventIdHeader() async throws {
        let captured = LockedRequestBox()
        MockURLProtocol.handler = { req in
            captured.set(req)
            return (httpOK(req.url),
                     Data("data: {\"type\":\"run.finished\",\"run_id\":\"r\",\"seq\":1,\"ts\":0,\"data\":{}}\n\n".utf8))
        }
        let client = makeClient(token: nil)
        for try await _ in client.stream(runId: "r", lastEventId: nil) {}
        let req = try #require(captured.get())
        #expect(req.value(forHTTPHeaderField: "Last-Event-ID") == nil)
        #expect(req.value(forHTTPHeaderField: "Authorization") == nil)
    }

    @Test("非 2xx：抛 APIError（404 运行不存在）", .resetMock)
    func httpError() async throws {
        MockURLProtocol.handler = { req in
            let resp = HTTPURLResponse(url: req.url!, statusCode: 404,
                                       httpVersion: nil, headerFields: nil)!
            return (resp, Data())
        }
        let client = makeClient()
        var iterator = client.stream(runId: "gone", lastEventId: nil).makeAsyncIterator()
        await #expect(throws: APIError.notFound) {
            _ = try await iterator.next()
        }
    }

    @Test("流尾无空行时残帧也产出", .resetMock)
    func trailingFrameWithoutBlankLine() async throws {
        MockURLProtocol.handler = { req in
            (httpOK(req.url),
             Data("id: 9\ndata: {\"type\":\"run.finished\",\"run_id\":\"r\",\"seq\":9,\"ts\":0,\"data\":{}}".utf8))
        }
        let client = makeClient()
        var frames: [SseFrame] = []
        for try await f in client.stream(runId: "r", lastEventId: nil) { frames.append(f) }
        #expect(frames.count == 1)
        if frames.count == 1 { #expect(frames[0].id == "9") }
    }
}
