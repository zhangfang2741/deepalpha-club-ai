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

    /// 批量拉自选列表里每只标的当前的中枢阶段——单独一个接口，比拉列表慢
    /// （要跑缠论分析），列表先展示出来，阶段标签异步补上。
    static func phases() async throws -> WatchlistPhasesResponse {
        try await APIClient.shared.get("/watchlist/phases")
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
