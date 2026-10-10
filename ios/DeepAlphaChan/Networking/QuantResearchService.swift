import Foundation

/// 量化研究与分析师评级接口。文案由后端按语言生成，这里只把 App 当前语言带上。
enum QuantResearchService {
    private static var lang: String { Localized.language() == .english ? "en" : "zh" }

    static func research(market: StockMarket, symbol: String) async throws -> QuantResearch {
        #if DEBUG && targetEnvironment(simulator)
        if let r: QuantResearch = fixture("quant_\(symbol.uppercased()).json") { return r }
        #endif
        return try await APIClient.shared.get("/quant-research/\(market.rawValue)/\(symbol.uppercased())",
                                       query: ["lang": lang])
    }

    static func methodology() async throws -> QuantMethodology {
        #if DEBUG && targetEnvironment(simulator)
        if let r: QuantMethodology = fixture("methodology.json") { return r }
        #endif
        return try await APIClient.shared.get("/quant-research/methodology", query: ["lang": lang])
    }

    /// 同阶段综合分排名：前 limit 家 + 本股位置（样本外股票按它自己的综合分估算名次）。
    /// 本机内存缓存 30 分钟（排名每天只随批量变一次），反复点开企业阶段不再等网络。
    static func stageRanking(market: String, stage: String, symbol: String?, score: Double?,
                             limit: Int = 30) async throws -> QuantStageRanking {
        var query = ["lang": lang, "stage": stage, "limit": String(limit)]
        if let symbol { query["symbol"] = symbol.uppercased() }
        if let score { query["score"] = String(format: "%.1f", score) }
        let key = market + "|" + query.sorted { $0.key < $1.key }.map { $0.key + "=" + $0.value }.joined(separator: "&")
        if let hit = await StageRankingCache.shared.get(key) { return hit }
        let fresh: QuantStageRanking = try await APIClient.shared.get("/quant-research/\(market)/stage-ranking", query: query)
        await StageRankingCache.shared.set(key, fresh)
        return fresh
    }

    /// 只给企业阶段弹层同步取缓存用（有缓存就不显示加载圈）
    static func cachedStageRanking(market: String, stage: String, symbol: String?, score: Double?,
                                   limit: Int = 30) async -> QuantStageRanking? {
        var query = ["lang": lang, "stage": stage, "limit": String(limit)]
        if let symbol { query["symbol"] = symbol.uppercased() }
        if let score { query["score"] = String(format: "%.1f", score) }
        let key = market + "|" + query.sorted { $0.key < $1.key }.map { $0.key + "=" + $0.value }.joined(separator: "&")
        return await StageRankingCache.shared.get(key)
    }

    /// 基本面动向雷达（每天随批量更新一次）；本机内存缓存 30 分钟。
    static func trendRadar(market: String) async throws -> QuantTrendRadar {
        let key = "trend|" + market + "|" + lang
        if let hit = await TrendRadarCache.shared.get(key) { return hit }
        let fresh: QuantTrendRadar = try await APIClient.shared.get("/quant-research/\(market)/trend-radar",
                                                                   query: ["lang": lang])
        await TrendRadarCache.shared.set(key, fresh)
        return fresh
    }

    /// kind：latest = 最新一份定期报告；annual = 最新年报
    static func latestReport(market: StockMarket, symbol: String, kind: String = "latest") async throws -> LatestReport {
        try await APIClient.shared.get("/quant-research/\(market.rawValue)/\(symbol.uppercased())/report",
                                       query: ["lang": lang, "kind": kind])
    }

    /// peek = true：只看有没有缓存好的 AI 总结，不触发生成
    static func reportSummary(market: StockMarket, symbol: String, kind: String = "latest",
                              peek: Bool = false) async throws -> ReportSummaryResponse {
        try await APIClient.shared.get("/quant-research/\(market.rawValue)/\(symbol.uppercased())/report/summary",
                                       query: ["lang": lang, "kind": kind, "peek": peek ? "true" : "false"])
    }

    static func analystOverview(market: StockMarket, symbol: String) async throws -> AnalystOverview {
        #if DEBUG && targetEnvironment(simulator)
        if let r: AnalystOverview = fixture("analyst_\(symbol.uppercased()).json") { return r }
        #endif
        // bucket_labels=1：本版本按响应里的五档名称显示（A 股 / 港股是买入 / 增持 / 中性 / 减持 / 卖出），
        // 后端只对带这个参数的请求返回 A 股 / 港股数据
        return try await APIClient.shared.get("/analyst-upgrades/overview/\(symbol.uppercased())",
                                       query: ["market": market.rawValue, "lang": lang, "bucket_labels": "1"])
    }

    #if DEBUG && targetEnvironment(simulator)
    /// 仅模拟器 Debug：设置 QUANT_FIXTURE_DIR 时从主机目录读后端生成的 JSON（新接口未上线前本地验收用）。
    private static func fixture<T: Decodable>(_ name: String) -> T? {
        guard let dir = ProcessInfo.processInfo.environment["QUANT_FIXTURE_DIR"],
              let data = try? Data(contentsOf: URL(fileURLWithPath: dir).appending(path: name)) else { return nil }
        return try? JSONDecoder().decode(T.self, from: data)
    }
    #endif
}

/// 同阶段排名的本机内存缓存（30 分钟；App 重启即清空）。
actor StageRankingCache {
    static let shared = StageRankingCache()
    private var store: [String: (at: Date, value: QuantStageRanking)] = [:]
    private let ttl: TimeInterval = 30 * 60

    func get(_ key: String) -> QuantStageRanking? {
        guard let hit = store[key], Date().timeIntervalSince(hit.at) < ttl else { return nil }
        return hit.value
    }

    func set(_ key: String, _ value: QuantStageRanking) {
        store[key] = (Date(), value)
    }
}

/// 基本面动向雷达的本机内存缓存（30 分钟；App 重启即清空）。
actor TrendRadarCache {
    static let shared = TrendRadarCache()
    private var store: [String: (at: Date, value: QuantTrendRadar)] = [:]
    private let ttl: TimeInterval = 30 * 60

    func get(_ key: String) -> QuantTrendRadar? {
        guard let hit = store[key], Date().timeIntervalSince(hit.at) < ttl else { return nil }
        return hit.value
    }

    func set(_ key: String, _ value: QuantTrendRadar) {
        store[key] = (Date(), value)
    }
}
