import Foundation

/// 雷达「基本面研究」tab：股票池里每天综合等级升 / 降的股票（GET /signal-radar/grade-events）；
/// 「分析师评级」tab 的 GET /signal-radar/analyst-events 返回同一形状（多几个可选字段），共用这些模型。
struct GradeEventsResponse: Decodable {
    let market: String
    let universeKey: String
    let universeName: String
    let days: [GradeDay]
    /// false = 评级数据读取失败（不是「没有事件」）。
    let available: Bool
    /// 分析师评级 tab：false = 该市场没有按日券商评级变动数据（A 股 / 港股）。
    let supported: Bool
    /// 分析师评级 tab：还在后台拉取的股票只数（>0 时事件可能不全）。
    let pendingSymbols: Int

    enum CodingKeys: String, CodingKey {
        case market, days, available, supported
        case universeKey = "universe_key"
        case universeName = "universe_name"
        case pendingSymbols = "pending_symbols"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        market = try c.decode(String.self, forKey: .market)
        universeKey = try c.decode(String.self, forKey: .universeKey)
        universeName = try c.decodeIfPresent(String.self, forKey: .universeName) ?? ""
        days = try c.decodeIfPresent([GradeDay].self, forKey: .days) ?? []
        available = try c.decodeIfPresent(Bool.self, forKey: .available) ?? true
        supported = try c.decodeIfPresent(Bool.self, forKey: .supported) ?? true
        pendingSymbols = try c.decodeIfPresent(Int.self, forKey: .pendingSymbols) ?? 0
    }
}

struct GradeDay: Decodable, Identifiable {
    let date: String
    let upCount: Int
    let downCount: Int
    let events: [GradeEvent]

    var id: String { date }

    enum CodingKeys: String, CodingKey {
        case date, events
        case upCount = "up_count"
        case downCount = "down_count"
    }
}

/// 一条事件：基本面 tab = 综合等级升 / 降（fromGrade / toGrade / steps = 档数）；
/// 分析师评级 tab = 券商净上调 / 下调（steps = 净家数，upgrades / downgrades / toBucket / firms）。两个接口共用。
struct GradeEvent: Decodable, Identifiable {
    let symbol: String
    let name: String
    let date: String
    /// up = 升档 / 净上调；down = 降档 / 净下调
    let direction: String
    let fromGrade: String
    let toGrade: String
    /// 变动档数（13 档字母等级）；分析师评级为净家数。
    let steps: Int
    let sector: String?
    let score: Double?
    /// 分析师评级：当天上调 / 下调家数、新评级归类（buy / hold / sell）、同方向券商。
    let upgrades: Int
    let downgrades: Int
    let toBucket: String
    let firms: [String]

    var id: String { "\(symbol)-\(date)" }
    var isUp: Bool { direction == "up" }

    enum CodingKeys: String, CodingKey {
        case symbol, name, date, direction, steps, sector, score, upgrades, downgrades, firms
        case fromGrade = "from_grade"
        case toGrade = "to_grade"
        case toBucket = "to_bucket"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        symbol = try c.decode(String.self, forKey: .symbol)
        name = try c.decode(String.self, forKey: .name)
        date = try c.decode(String.self, forKey: .date)
        direction = try c.decode(String.self, forKey: .direction)
        fromGrade = try c.decodeIfPresent(String.self, forKey: .fromGrade) ?? ""
        toGrade = try c.decodeIfPresent(String.self, forKey: .toGrade) ?? ""
        steps = try c.decode(Int.self, forKey: .steps)
        sector = try c.decodeIfPresent(String.self, forKey: .sector)
        score = try c.decodeIfPresent(Double.self, forKey: .score)
        upgrades = try c.decodeIfPresent(Int.self, forKey: .upgrades) ?? 0
        downgrades = try c.decodeIfPresent(Int.self, forKey: .downgrades) ?? 0
        toBucket = try c.decodeIfPresent(String.self, forKey: .toBucket) ?? ""
        firms = try c.decodeIfPresent([String].self, forKey: .firms) ?? []
    }
}
