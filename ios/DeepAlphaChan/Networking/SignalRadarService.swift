import Foundation

/// 信号雷达接口封装。
enum SignalRadarService {
    /// 拉取某市场的信号雷达（首次可能返回 status=generating，需前端轮询）。
    static func fetch(market: String, refresh: Bool = false) async throws -> SignalRadarResponse {
        var query = ["market": market]
        if refresh { query["refresh"] = "true" }
        return try await APIClient.shared.get("/signal-radar", query: query)
    }
}
