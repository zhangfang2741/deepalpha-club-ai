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

    /// 免费预览：未订阅高级版用户唯一能点开的一天（后端固定算「上个月 1 号」，
    /// 随当前月份自动滚动；遇非交易日取之前最近交易日），真实数据，按所选 universe
    /// 计算（nil = 市场默认），可能返回 status=generating 需要轮询。
    static func demo(market: String, universe: String? = nil) async throws -> SignalRadarResponse {
        var query = ["market": market]
        if let universe, !universe.isEmpty { query["universe"] = universe }
        return try await APIClient.shared.get("/signal-radar/demo", query: query)
    }
}
