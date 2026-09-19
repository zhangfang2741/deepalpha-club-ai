import Foundation

/// 三地恐慌指数：美股 VIX(CNN Fear&Greed) / A股上证指数 / 港股恒生指数，
/// 统一折算成 0~100 分（越低越恐慌）。A股/港股是指数收盘价的 RSI(14)。
struct PanicIndexResponse: Decodable {
    let market: String
    let label: String
    let current: PanicIndexSnapshot
    let previousWeek: PanicIndexSnapshot
    let previousMonth: PanicIndexSnapshot
    let history: [PanicIndexPoint]

    enum CodingKeys: String, CodingKey {
        case market, label, current, history
        case previousWeek = "previous_week"
        case previousMonth = "previous_month"
    }
}

/// 特定时间点的快照（当前 / 一周前 / 一月前）。
struct PanicIndexSnapshot: Decodable {
    let score: Double
    let rating: String
    let date: String?
    let rawValue: Double?

    enum CodingKeys: String, CodingKey {
        case score, rating, date
        case rawValue = "raw_value"
    }
}

/// 历史曲线上的单个数据点。
struct PanicIndexPoint: Decodable, Identifiable {
    let date: String
    let score: Double
    let rating: String
    let rawValue: Double?

    var id: String { date }

    enum CodingKeys: String, CodingKey {
        case date, score, rating
        case rawValue = "raw_value"
    }
}
