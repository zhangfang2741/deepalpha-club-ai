import Foundation

/// 信号雷达接口封装。
enum SignalRadarService {
    /// 好股票门槛口径：恒为 good（后端 good_xm 去掉动量的实验口径只留给调试脚本，App 不再提供开关）。
    static var qualityMode: String { "good" }

    /// 拉取某 (市场, universe) 的信号雷达（首次可能返回 status=generating，需前端轮询）。
    /// universe 传 nil 时后端用该市场默认（大盘宽基）。
    static func fetch(
        market: String, universe: String? = nil, refresh: Bool = false
    ) async throws -> SignalRadarResponse {
        // quality=good：只留当前综合等级达标的股票的买卖点（门槛由后端定），并带分析师角标
        var query = ["market": market, "mode": SignalMode.current(), "scope": "all", "quality": qualityMode]
        if let universe, !universe.isEmpty { query["universe"] = universe }
        if refresh { query["refresh"] = "true" }
        let data = try await APIClient.shared.getData("/signal-radar", query: query)
        let resp = try JSONDecoder().decode(SignalRadarResponse.self, from: data)
        // 就绪的结果落盘：下次打开 App 先显示它（键与 ViewModel 的内存缓存键一致）
        if !resp.isGenerating, !resp.days.isEmpty, !resp.universe.isEmpty, resp.universe != RadarUniverse.watchlistKey {
            RadarDiskCache.write("\(market)|\(resp.universe)|\(SignalMode.current())", data)
        }
        return resp
    }

    /// 免费预览：未订阅会员用户唯一能点开的一天（后端固定算「上个月 1 号」，
    /// 随当前月份自动滚动；遇非交易日取之前最近交易日），真实数据，按所选 universe
    /// 计算（nil = 市场默认），可能返回 status=generating 需要轮询。
    static func demo(market: String, universe: String? = nil) async throws -> SignalRadarResponse {
        var query = ["market": market, "mode": SignalMode.current(), "scope": "all", "quality": qualityMode]
        if let universe, !universe.isEmpty { query["universe"] = universe }
        let data = try await APIClient.shared.getData("/signal-radar/demo", query: query)
        let resp = try JSONDecoder().decode(SignalRadarResponse.self, from: data)
        if !resp.isGenerating, !resp.days.isEmpty, !resp.universe.isEmpty {
            RadarDiskCache.write("demo|\(market)|\(resp.universe)|\(SignalMode.current())", data)
        }
        return resp
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
