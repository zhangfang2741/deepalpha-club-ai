import Foundation

/// VM 依赖的业务端点抽象（测试注入 mock）。
public protocol TradingDeskServicing: Sendable {
    /// 创建运行，返回 run_id。
    func createRun(ticker: String) async throws -> String
    /// 控制（pause/resume/inject/cancel）。
    func control(runId: String, action: ControlAction, text: String?) async throws
    /// 历史列表（ticker 过滤可选，服务端分页）。
    func listRuns(ticker: String?, limit: Int, offset: Int) async throws -> RunListResponse
    /// 单条详情（回放）。
    func getRun(runId: String) async throws -> RunDetailResponse
    /// SSE 订阅（lastEventId 断线续读）。
    func stream(runId: String, lastEventId: String?) -> AsyncThrowingStream<SseFrame, Error>
}

/// 线上实现：组合 APIClient + SSEClient。
public struct TradingDeskService: TradingDeskServicing {
    let api: APIClient
    let sse: SSEClient

    public init(api: APIClient, sse: SSEClient) {
        self.api = api
        self.sse = sse
    }

    public func createRun(ticker: String) async throws -> String {
        struct Body: Encodable { let ticker: String }
        struct Resp: Decodable { let runId: String
            enum CodingKeys: String, CodingKey { case runId = "run_id" } }
        let resp: Resp = try await api.post("/api/v1/trading-desk/runs", json: Body(ticker: ticker))
        return resp.runId
    }

    public func control(runId: String, action: ControlAction, text: String?) async throws {
        struct Body: Encodable { let action: String; let text: String? }
        struct Resp: Decodable { let accepted: Bool }
        let _: Resp = try await api.post(
            "/api/v1/trading-desk/runs/\(runId)/control",
            json: Body(action: action.rawValue, text: text))
    }

    public func listRuns(ticker: String?, limit: Int, offset: Int) async throws -> RunListResponse {
        var query: [String: String] = ["limit": String(limit), "offset": String(offset)]
        if let t = ticker?.trimmingCharacters(in: .whitespaces).uppercased(), !t.isEmpty {
            query["ticker"] = t
        }
        return try await api.get("/api/v1/trading-desk/runs", query: query)
    }

    public func getRun(runId: String) async throws -> RunDetailResponse {
        try await api.get("/api/v1/trading-desk/runs/\(runId)")
    }

    public func stream(runId: String, lastEventId: String?) -> AsyncThrowingStream<SseFrame, Error> {
        sse.stream(runId: runId, lastEventId: lastEventId)
    }
}
