import Foundation

/// 一条已解析的 SSE 帧：id 供断线续读（Last-Event-ID），event 是载荷。
public struct SseFrame: Sendable, Equatable {
    public let id: String?
    public let event: TradingDeskEvent
    public init(id: String?, event: TradingDeskEvent) {
        self.id = id
        self.event = event
    }
}

/// SSE 帧解析纯函数。帧格式（后端 app/api/v1/trading_desk.py stream_run）：
/// `id: <RedisStreamId>\ndata: <json 一行>\n\n`。
/// 多行 data 按 SSE 规范以 \n join；坏 JSON 返回 nil 丢弃，不掐断流。
public enum SSEFrameParser {
    public static func parse(_ raw: String) -> SseFrame? {
        var id: String?
        var dataLines: [String] = []
        for line in raw.split(separator: "\n", omittingEmptySubsequences: false) {
            if line.hasPrefix("id:") {
                id = line.dropFirst(3).trimmingCharacters(in: .whitespaces)
            } else if line.hasPrefix("data:") {
                dataLines.append(String(line.dropFirst(5)))
            }
            // 其余（注释行、event:、retry:）忽略
        }
        guard !dataLines.isEmpty else { return nil }
        let json = dataLines.joined(separator: "\n")
        guard let jsonData = json.data(using: .utf8),
              let event = try? JSONDecoder().decode(TradingDeskEvent.self, from: jsonData)
        else { return nil }
        return SseFrame(id: id, event: event)
    }
}
