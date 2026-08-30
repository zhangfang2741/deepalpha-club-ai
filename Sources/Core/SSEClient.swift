import Foundation

/// SSE 订阅：GET /api/v1/trading-desk/runs/{id}/stream（Accept: text/event-stream）。
/// 续读用 Last-Event-ID 请求头（Redis Stream ID）。重连策略由调用方
/// （TradingDeskViewModel.runLoop）负责——client 只做单连接生命周期。
public struct SSEClient: Sendable {
    public let baseURL: URL
    public let session: URLSession
    public let tokenProvider: @Sendable () -> String?

    public init(baseURL: URL,
                session: URLSession = .shared,
                tokenProvider: @escaping @Sendable () -> String? = { nil }) {
        self.baseURL = baseURL
        self.session = session
        self.tokenProvider = tokenProvider
    }

    public func stream(runId: String, lastEventId: String?) -> AsyncThrowingStream<SseFrame, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    guard let url = URL(string: "\(baseURL.absoluteString)/api/v1/trading-desk/runs/\(runId)/stream") else {
                        throw APIError.decoding
                    }
                    var request = URLRequest(url: url)
                    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    if let token = tokenProvider() {
                        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                    }
                    if let last = lastEventId {
                        request.setValue(last, forHTTPHeaderField: "Last-Event-ID")
                    }
                    let (bytes, response) = try await session.bytes(for: request)
                    guard let http = response as? HTTPURLResponse else { throw APIError.network }
                    guard (200..<300).contains(http.statusCode) else {
                        // 读掉 body 以便错误映射拿到 detail
                        var body = Data()
                        for try await b in bytes { body.append(b) }
                        throw APIError.from(status: http.statusCode, body: body)
                    }
                    // 手动按 \n 分行（AsyncLineSequence 会跳过空行，
                    // 而 SSE 以空行分帧——不能用它）。
                    var buffer = ""
                    var pending = Data()
                    for try await chunk in bytes {
                        if Task.isCancelled { break }
                        pending.append(chunk)
                        while let nl = pending.firstIndex(of: UInt8(ascii: "\n")) {
                            let lineData = pending[pending.startIndex..<nl]
                            pending.removeSubrange(pending.startIndex...nl)
                            var line = String(decoding: lineData, as: UTF8.self)
                            if line.hasSuffix("\r") { line.removeLast() }

                            if line.isEmpty {                 // 空行 = 帧边界
                                if let frame = SSEFrameParser.parse(buffer) {
                                    continuation.yield(frame)
                                }
                                buffer = ""
                            } else if line.hasPrefix(":") {  // 心跳注释行
                                continue
                            } else {
                                buffer += buffer.isEmpty ? line : "\n" + line
                            }
                        }
                    }
                    if Task.isCancelled {
                        continuation.finish()
                    } else {
                        // 流被服务端关掉且最后一帧后无空行：
                        // 把 pending 里的末行（无换行结尾）并入 buffer 再刷残帧
                        if !pending.isEmpty {
                            let line = String(decoding: pending, as: UTF8.self)
                            if !line.isEmpty && !line.hasPrefix(":") {
                                buffer += buffer.isEmpty ? line : "\n" + line
                            }
                        }
                        if !buffer.isEmpty, let frame = SSEFrameParser.parse(buffer) {
                            continuation.yield(frame)
                        }
                        continuation.finish()
                    }
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
}
