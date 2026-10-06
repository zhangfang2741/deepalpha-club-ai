import Foundation

/// 信号雷达接口封装。
enum SignalRadarService {
    /// 好股票门槛口径：good（默认）/ good_xm（去掉动量维度）。仅 DEBUG 构建可通过「我的」页开关切换，正式版恒为 good。
    static var qualityMode: String {
        #if DEBUG
        return UserDefaults.standard.bool(forKey: "radar_quality_ex_momentum") ? "good_xm" : "good"
        #else
        return "good"
        #endif
    }

    /// 拉取某 (市场, universe) 的信号雷达（首次可能返回 status=generating，需前端轮询）。
    /// universe 传 nil 时后端用该市场默认（大盘宽基）。
    static func fetch(
        market: String, universe: String? = nil, refresh: Bool = false
    ) async throws -> SignalRadarResponse {
        // quality=good：只留当前综合等级达标的股票的买卖点（门槛由后端定），并带分析师角标
        var query = ["market": market, "mode": SignalMode.current(), "scope": "all", "quality": qualityMode]
        if let universe, !universe.isEmpty { query["universe"] = universe }
        if refresh { query["refresh"] = "true" }
        return try await APIClient.shared.get("/signal-radar", query: query)
    }

    /// 免费预览：未订阅会员用户唯一能点开的一天（后端固定算「上个月 1 号」，
    /// 随当前月份自动滚动；遇非交易日取之前最近交易日），真实数据，按所选 universe
    /// 计算（nil = 市场默认），可能返回 status=generating 需要轮询。
    static func demo(market: String, universe: String? = nil) async throws -> SignalRadarResponse {
        var query = ["market": market, "mode": SignalMode.current(), "scope": "all", "quality": qualityMode]
        if let universe, !universe.isEmpty { query["universe"] = universe }
        return try await APIClient.shared.get("/signal-radar/demo", query: query)
    }

    /// 好股票名单：某 (市场, universe) 当前综合等级最高的若干只（含近 90 天券商评级净上调 / 下调，仅美股）。
    static func fundamentalTop(market: String, universe: String? = nil, sector: String? = nil, limit: Int = 50) async throws -> FundamentalTopResponse {
        var query = ["market": market, "limit": String(limit)]
        if let universe, !universe.isEmpty { query["universe"] = universe }
        // 选了行业：后端先按行业过滤再取前 limit 只，名单才不会因为全池前 50 里没有该行业而变空
        if let sector, !sector.isEmpty { query["sector"] = sector }
        return try await APIClient.shared.get("/signal-radar/fundamental-top", query: query)
    }
}
