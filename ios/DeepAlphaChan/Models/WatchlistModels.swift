import Foundation

/// 自选股条目。日期沿用项目内其它 model 的惯例保留原始字符串，不解成 Date——
/// 列表只按后端返回顺序展示，不需要在端上再做时间运算。
struct WatchlistItem: Decodable, Identifiable {
    let market: String
    let symbol: String
    let name: String
    let createdAt: String

    var id: String { "\(market):\(symbol)" }

    enum CodingKeys: String, CodingKey {
        case market, symbol, name
        case createdAt = "created_at"
    }
}

struct WatchlistResponse: Decodable {
    let items: [WatchlistItem]
}
