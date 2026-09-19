import Foundation

/// 三地恐慌指数接口封装。
enum PanicIndexService {
    static func fetch(market: String) async throws -> PanicIndexResponse {
        try await APIClient.shared.get("/panic-index", query: ["market": market])
    }
}
