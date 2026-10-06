import Foundation

/// 雷达「基本面研究」tab：股票池里当前综合等级最高的若干只股票（GET /signal-radar/fundamental-top）。
struct FundamentalTopResponse: Decodable {
    let market: String
    let universeKey: String
    let universeName: String
    /// 最新评级日。
    let asOf: String?
    /// 股票池里有评级的只数。
    let rated: Int
    let items: [FundamentalItem]
    /// false = 评级数据读取失败（不是「没有评级」）。
    let available: Bool
    /// false = 该市场没有券商评级变动数据（A 股 / 港股），气泡不画分析师角标。
    let analystSupported: Bool
    /// 还在后台拉取券商评级的只数（>0 时角标可能不全）。
    let analystPending: Int

    enum CodingKeys: String, CodingKey {
        case market, rated, items, available
        case universeKey = "universe_key"
        case universeName = "universe_name"
        case asOf = "as_of"
        case analystSupported = "analyst_supported"
        case analystPending = "analyst_pending"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        market = try c.decode(String.self, forKey: .market)
        universeKey = try c.decode(String.self, forKey: .universeKey)
        universeName = try c.decodeIfPresent(String.self, forKey: .universeName) ?? ""
        asOf = try c.decodeIfPresent(String.self, forKey: .asOf)
        rated = try c.decodeIfPresent(Int.self, forKey: .rated) ?? 0
        items = try c.decodeIfPresent([FundamentalItem].self, forKey: .items) ?? []
        available = try c.decodeIfPresent(Bool.self, forKey: .available) ?? true
        analystSupported = try c.decodeIfPresent(Bool.self, forKey: .analystSupported) ?? true
        analystPending = try c.decodeIfPresent(Int.self, forKey: .analystPending) ?? 0
    }
}

struct FundamentalItem: Decodable, Identifiable {
    let symbol: String
    let name: String
    /// 综合等级 A+ ~ F。
    let grade: String
    let score: Double?
    let asOf: String
    let sector: String?
    /// 近 30 天券商上调 / 下调家数；nil = 没有数据（A 股 / 港股，或还没拉到）。
    let analystUp: Int?
    let analystDown: Int?

    var id: String { symbol }

    /// 分析师角标：净上调「▲n」、净下调「▼n」；净 0 或没有数据返回 nil。
    var analystMark: String? {
        guard let up = analystUp, let down = analystDown, up != down else { return nil }
        return up > down ? "▲\(up - down)" : "▼\(down - up)"
    }

    enum CodingKeys: String, CodingKey {
        case symbol, name, grade, score, sector
        case asOf = "as_of"
        case analystUp = "analyst_up"
        case analystDown = "analyst_down"
    }
}
