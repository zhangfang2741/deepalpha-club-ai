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

    /// 列表副标题用的显示名：只有当 name 是真正有别于代码的名称时才返回。
    /// 后端拿不到名称时会把 name 回落成代码本身（如「2015」的 name 也是「2015」），
    /// 这时返回 nil，避免副标题原样重复上面的代码（「NVDA / NVDA」这种）。
    var displayName: String? {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty,
              trimmed.caseInsensitiveCompare(symbol) != .orderedSame else { return nil }
        return trimmed
    }
}

struct WatchlistResponse: Decodable {
    let items: [WatchlistItem]
}
