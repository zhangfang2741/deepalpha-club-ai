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
    /// 形态技术面强度 0~1（决定气泡颜色深浅；气泡大小由 `level` 决定，见下）
    let strength: Double
    let bias: String
    let signalStrength: String
    let confirmed: Bool

    var id: String { "\(symbol)-\(date)-\(signalType)" }
    var isBuy: Bool { side == "buy" }

    /// 买卖点级别：1/2/3，取 signalType 末位数字（"buy2"/"sell2" 都取到 2），
    /// 对买卖两侧通用。级别决定气泡大小（潜在行情空间），映射见
    /// SignalRadarView.diameter(forLevel:)——一类能吃到从底部开始的整段反转，
    /// 气泡最大；三类只剩突破后的延续段，气泡最小。级别的"确定性"改由
    /// `confirmed` 字段驱动气泡边框虚实表达，不叠加到大小上。
    var level: Int {
        Int(String(signalType.suffix(1))) ?? 1
    }

    enum CodingKeys: String, CodingKey {
        case symbol, name, side, label, date, price, strength, bias, confirmed
        case signalType = "signal_type"
        case signalStrength = "signal_strength"
    }
}
