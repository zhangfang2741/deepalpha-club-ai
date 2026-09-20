import Foundation

/// 信号雷达接口封装。
enum SignalRadarService {
    /// 拉取某 (市场, universe) 的信号雷达（首次可能返回 status=generating，需前端轮询）。
    /// universe 传 nil 时后端用该市场默认（科技指数）。
    static func fetch(
        market: String, universe: String? = nil, refresh: Bool = false
    ) async throws -> SignalRadarResponse {
        var query = ["market": market]
        if let universe, !universe.isEmpty { query["universe"] = universe }
        if refresh { query["refresh"] = "true" }
        return try await APIClient.shared.get("/signal-radar", query: query)
    }
}
