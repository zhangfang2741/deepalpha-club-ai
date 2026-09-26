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
    /// 自选上限，按请求带的订阅档位算出，来自后端 `app.services.watchlist.TIER_LIMITS`，
    /// 不在端上硬编码。nil 表示该档不限（高级版）。
    let maxItems: Int?

    enum CodingKeys: String, CodingKey {
        case items
        case maxItems = "max_items"
    }
}

/// 一只自选标的当前的中枢生命周期阶段（对应后端 WatchlistPhaseOut）。
/// 结构没成形或行情拉取失败时 phase/phaseLabel 为 nil，UI 不显示标签。
struct WatchlistPhase: Decodable {
    let symbol: String
    let market: String
    let phase: String?
    let phaseLabel: String?
    /// 离开中枢的方向 up/down，配色用（Theme.phaseColor）；旧后端没有这个字段时为 nil。
    let direction: String?

    enum CodingKeys: String, CodingKey {
        case symbol, market, phase, direction
        case phaseLabel = "phase_label"
    }
}

struct WatchlistPhasesResponse: Decodable {
    /// key 为 `{market}:{symbol}`，与 WatchlistItem.id 同一套拼法，直接查表用。
    let phases: [String: WatchlistPhase]
}
