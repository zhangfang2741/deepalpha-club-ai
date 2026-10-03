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
