import Foundation

/// 八字排盘/AI 解读接口（协议化方便测试 mock）。
public protocol BaziServicing: Sendable {
    func getChart(_ request: BaziChartRequest) async throws -> BaziChartResponse
    func getInterpretation(_ request: InterpretationRequest) async throws -> InterpretationResponse
}

/// 线上实现：POST /api/v1/bazi/chart 、 POST /api/v1/bazi/interpretation。
public struct BaziService: BaziServicing {
    let api: APIClient

    public init(api: APIClient) {
        self.api = api
    }

    public func getChart(_ request: BaziChartRequest) async throws -> BaziChartResponse {
        try await api.post("/api/v1/bazi/chart", json: request)
    }

    public func getInterpretation(_ request: InterpretationRequest) async throws -> InterpretationResponse {
        try await api.post("/api/v1/bazi/interpretation", json: request)
    }
}
