import Foundation

/// 一个可选的扫描 universe（科技窄基 / 大盘宽基），供左上角切换器用。
struct RadarUniverse: Decodable, Identifiable, Equatable {
    let key: String       // nasdaq100 / sp500 …
    let name: String      // 纳斯达克100 / 标普500 …
    let isDefault: Bool

    var id: String { key }

    enum CodingKeys: String, CodingKey {
        case key, name
        case isDefault = "is_default"
    }
}

/// 信号雷达：某 (市场, universe) 最近若干交易日的每日缠论买卖点。
struct SignalRadarResponse: Decodable {
    let market: String
    /// 当前 universe 键 + 可选项：给默认值，兼容部署切换期缺字段的旧缓存响应。
    var universe: String = ""
    var universes: [RadarUniverse] = []
    let etfName: String
    let universeSize: Int
    let asOf: String
    let topN: Int
    let days: [RadarDay]
    let status: String   // ready / generating

    enum CodingKeys: String, CodingKey {
        case market
        case universe
        case universes
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
    /// 形态技术面强度 0~1：同时决定气泡的颜色深浅与大小（越强既深又大），见
    /// SignalRadarView.bubbleColor / diameter(forStrength:)。
    let strength: Double
    let bias: String
    let signalStrength: String
    let confirmed: Bool

    var id: String { "\(symbol)-\(date)-\(signalType)" }
    var isBuy: Bool { side == "buy" }

    /// 买卖点级别：1/2/3，取 signalType 末位数字（"buy2"/"sell2" 都取到 2），
    /// 对买卖两侧通用。级别代表潜在行情空间（一类能吃到从底部开始的整段反转，
    /// 三类只剩突破后的延续段），在雷达里以气泡左上角小角标标注，不再占用大小
    /// 维度——大小已改为与颜色深浅同向表达强度，见 SignalRadarView.levelLabel /
    /// diameter(forStrength:)。
    var level: Int {
        Int(String(signalType.suffix(1))) ?? 1
    }

    enum CodingKeys: String, CodingKey {
        case symbol, name, side, label, date, price, strength, bias, confirmed
        case signalType = "signal_type"
        case signalStrength = "signal_strength"
    }
}
