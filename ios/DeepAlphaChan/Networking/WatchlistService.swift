import Foundation

/// 自选股接口封装。
enum WatchlistService {
    private struct AddBody: Encodable {
        let market: String
        let symbol: String
        let name: String
    }

    private struct RemoveResult: Decodable {
        let removed: Bool
    }

    static func list() async throws -> WatchlistResponse {
        try await APIClient.shared.get("/watchlist")
    }

    static func add(market: StockMarket, symbol: String, name: String) async throws -> WatchlistItem {
        try await APIClient.shared.postJSON(
            "/watchlist",
            body: AddBody(market: market.rawValue, symbol: symbol, name: name)
        )
    }

    static func remove(market: StockMarket, symbol: String) async throws {
        let _: RemoveResult = try await APIClient.shared.delete("/watchlist/\(market.rawValue)/\(symbol)")
    }
}
