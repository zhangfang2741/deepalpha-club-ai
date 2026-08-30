import Foundation
import Testing

/// URLProtocol mock：handler 返回 (response, data) 或抛错模拟网络失败。
/// SSE 流式测试通过 body 直传（URLProtocol 层面无需真实分块）。
final class MockURLProtocol: URLProtocol {
    /// 全局 handler（每个测试 reset 覆盖）。测试串行执行，无竞争。
    nonisolated(unsafe) static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    static func makeSession() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        return URLSession(configuration: config)
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = MockURLProtocol.handler else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
            return
        }
        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

/// 每个 @Test 前重置 handler 的 trait（Swift Testing 无 setUp）。
struct ResetMock: TestTrait, TestScoping {
    func provideScope(for test: Test, testCase: Test.Case?,
                      performing function: @Sendable () async throws -> Void) async throws {
        MockURLProtocol.handler = nil
        try await function()
    }
}

extension TestTrait where Self == ResetMock {
    static var resetMock: ResetMock { ResetMock() }
}

/// 跨闭包捕获请求的线程安全盒子。
final class LockedRequestBox: @unchecked Sendable {
    private let lock = NSLock()
    private var req: URLRequest?
    func set(_ r: URLRequest) { lock.lock(); req = r; lock.unlock() }
    func get() -> URLRequest? { lock.lock(); defer { lock.unlock() }; return req }
}

extension URLRequest {
    /// URLProtocol 场景 body 可能落在 httpBodyStream，读出来便于断言。
    var httpBodyStreamData: Data? {
        guard let stream = httpBodyStream else { return nil }
        stream.open()
        defer { stream.close() }
        var data = Data()
        let bufSize = 4096
        let buf = UnsafeMutablePointer<UInt8>.allocate(capacity: bufSize)
        defer { buf.deallocate() }
        while stream.hasBytesAvailable {
            let n = stream.read(buf, maxLength: bufSize)
            if n <= 0 { break }
            data.append(buf, count: n)
        }
        return data
    }
}
