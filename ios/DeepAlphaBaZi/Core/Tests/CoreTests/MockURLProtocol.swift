import Foundation
import Testing

/// 每个测试自己的假服务器：一个 URLSession + 一个 handler。
///
/// Swift Testing 默认**并行**执行测试，共享一个静态 handler 会互相串味
/// （A 测试的 404 响应被 B 测试收到）。这里给每个 MockServer 分配唯一 id，
/// 写进 session 的 httpAdditionalHeaders，URLProtocol 按请求头回查自己的 handler。
final class MockServer: @unchecked Sendable {
    typealias Handler = @Sendable (URLRequest) throws -> (HTTPURLResponse, Data)

    let id = UUID().uuidString
    private let lock = NSLock()
    private var _handler: Handler?

    var handler: Handler? {
        get { lock.lock(); defer { lock.unlock() }; return _handler }
        set { lock.lock(); _handler = newValue; lock.unlock() }
    }

    lazy var session: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        config.httpAdditionalHeaders = [MockURLProtocol.idHeader: id]
        return URLSession(configuration: config)
    }()

    init() { MockURLProtocol.register(self) }
}

/// 按 X-Mock-Id 请求头把请求路由到对应 MockServer 的 handler。
final class MockURLProtocol: URLProtocol {
    static let idHeader = "X-Mock-Id"

    /// 注册表持有强引用：测试里 MockServer 常只被局部变量持有，
    /// ARC 可能在请求飞行途中就回收它，故由注册表兜底（测试进程内的少量常驻无妨）。
    nonisolated(unsafe) private static var servers: [String: MockServer] = [:]
    private static let registryLock = NSLock()

    static func register(_ server: MockServer) {
        registryLock.lock()
        servers[server.id] = server
        registryLock.unlock()
    }

    private static func server(for id: String) -> MockServer? {
        registryLock.lock()
        defer { registryLock.unlock() }
        return servers[id]
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let id = request.value(forHTTPHeaderField: MockURLProtocol.idHeader),
              let handler = MockURLProtocol.server(for: id)?.handler
        else {
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
