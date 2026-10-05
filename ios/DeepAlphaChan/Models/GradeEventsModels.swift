import Foundation

/// 雷达「基本面研究」tab：股票池里每天综合等级升 / 降的股票（GET /signal-radar/grade-events）。
struct GradeEventsResponse: Decodable {
    let market: String
    let universeKey: String
    let universeName: String
    let days: [GradeDay]
    /// false = 评级数据读取失败（不是「没有事件」）。
    let available: Bool

    enum CodingKeys: String, CodingKey {
        case market, days, available
        case universeKey = "universe_key"
        case universeName = "universe_name"
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

struct GradeEvent: Decodable, Identifiable {
    let symbol: String
    let name: String
    let date: String
    /// up = 升档 / down = 降档
    let direction: String
    let fromGrade: String
    let toGrade: String
    /// 变动档数（13 档字母等级）。
    let steps: Int
    let sector: String?
    let score: Double?

    var id: String { "\(symbol)-\(date)" }
    var isUp: Bool { direction == "up" }

    enum CodingKeys: String, CodingKey {
        case symbol, name, date, direction, steps, sector, score
        case fromGrade = "from_grade"
        case toGrade = "to_grade"
    }
}
