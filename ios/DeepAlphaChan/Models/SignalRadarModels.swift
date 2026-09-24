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
    /// 形态技术面强度 0~1（决定看板淘汰排序；气泡大小由 `level` 决定，
    /// 颜色深浅由 `pivotStageDepth` 决定，见下）
    let strength: Double
    let bias: String
    let signalStrength: String
    let confirmed: Bool
    /// 该信号发生当天的中枢生命周期阶段深浅 0~1：形成中枢=浅/中枢震荡=中/
    /// 已离开中枢=深，决定气泡颜色深浅（见 SignalRadarView.bubbleColor）。
    let pivotStageDepth: Double
    /// 次级别确认结论（日线定方向 × 30 分钟找买卖点），只有最新交易日的入榜气泡有；
    /// 可选字段，后端未部署或旧缓存里缺失时为 nil。
    let subLevelVerdict: String?
    let subLevelLabel: String?

    var id: String { "\(symbol)-\(date)-\(signalType)" }

    /// 日线与 30 分钟同向（共振买点/共振卖点），气泡上加标记。
    var isSubLevelResonance: Bool {
        subLevelVerdict == "resonance_buy" || subLevelVerdict == "resonance_sell"
    }
    var isBuy: Bool { side == "buy" }

    /// 买卖点级别：1/2/3，取 signalType 末位数字（"buy2"/"sell2" 都取到 2），
    /// 对买卖两侧通用。级别决定气泡大小（该类买卖点本身的确定性），映射见
    /// SignalRadarView.diameter(forLevel:)——一类只是背驰迹象、尚待验证，
    /// 气泡最小；三类回踩完全不回中枢是最强确认，气泡最大。单条信号自己
    /// 「有没有走完」是另一件事，由 `confirmed` 字段驱动气泡边框虚实表达，
    /// 不叠加到大小上。
    var level: Int {
        Int(String(signalType.suffix(1))) ?? 1
    }

    enum CodingKeys: String, CodingKey {
        case symbol, name, side, label, date, price, strength, bias, confirmed
        case signalType = "signal_type"
        case signalStrength = "signal_strength"
        case pivotStageDepth = "pivot_stage_depth"
        case subLevelVerdict = "sub_level_verdict"
        case subLevelLabel = "sub_level_label"
    }
}
