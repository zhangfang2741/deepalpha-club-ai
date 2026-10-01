import Foundation

/// 宏观 / 行业接口。文案由后端按语言生成，这里只把 App 当前语言带上。
enum MarketOverviewService {
    private static var lang: String { Localized.language() == .english ? "en" : "zh" }

    static func overview(market: StockMarket) async throws -> MarketOverview {
        try await APIClient.shared.get("/macro/\(market.rawValue)/overview", query: ["lang": lang])
    }

    static func macro(market: StockMarket) async throws -> MacroResponse {
        try await APIClient.shared.get("/macro/\(market.rawValue)", query: ["lang": lang])
    }

    static func sectors(market: StockMarket, parent: String? = nil) async throws -> SectorBoard {
        var query = ["lang": lang]
        if let parent { query["parent"] = parent }
        return try await APIClient.shared.get("/macro/\(market.rawValue)/sectors", query: query)
    }

    static func sectorPools(market: StockMarket, universe: String, date: String) async throws -> RadarSectorPools {
        try await APIClient.shared.get("/signal-radar/sector-pools", query: [
            "market": market.rawValue, "universe": universe, "date": date, "mode": SignalMode.current(),
        ])
    }
}
