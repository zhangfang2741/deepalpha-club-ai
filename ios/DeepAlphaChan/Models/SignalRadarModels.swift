import Foundation

/// 信号雷达：某市场最近若干交易日的每日缠论买卖点。
struct SignalRadarResponse: Decodable {
    let market: String
    let etfName: String
    let universeSize: Int
    let asOf: String
    let topN: Int
    let days: [RadarDay]
    let status: String   // ready / generating

    enum CodingKeys: String, CodingKey {
        case market
        case etfName = "etf_name"
        case universeSize = "universe_size"
        case asOf = "as_of"
        case topN = "top_n"
        case days
        case status
    }

    var isGenerating: Bool { status == "generating" }
}

/// 单个交易日的信号快照。
struct RadarDay: Decodable, Identifiable {
    let date: String
    let buyCount: Int
    let sellCount: Int
    let signals: [RadarSignal]

    var id: String { date }
    var total: Int { signals.count }

    enum CodingKeys: String, CodingKey {
        case date
        case buyCount = "buy_count"
        case sellCount = "sell_count"
        case signals
    }
}

/// 单只股票的当日买卖点信号。
struct RadarSignal: Decodable, Identifiable {
    let symbol: String
    let name: String
    let side: String          // buy / sell
    let label: String         // 一买 / 二卖 …
    let signalType: String    // buy1 / sell1 …
    let date: String
    let price: Double
    /// 形态技术面强度 0~1（同时决定气泡大小与颜色深浅）
    let strength: Double
    let bias: String
    let signalStrength: String
    let confirmed: Bool

    var id: String { "\(symbol)-\(date)-\(signalType)" }
    var isBuy: Bool { side == "buy" }

    enum CodingKeys: String, CodingKey {
        case symbol, name, side, label, date, price, strength, bias, confirmed
        case signalType = "signal_type"
        case signalStrength = "signal_strength"
    }
}
