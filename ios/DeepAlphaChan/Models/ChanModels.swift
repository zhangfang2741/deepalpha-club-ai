import Foundation

// MARK: - 缠论分析响应（对应 app/schemas/chan.py 的 ChanAnalysisResponse）

/// 合并后的 K 线（缠论按包含关系处理过）。
struct MergedCandle: Codable, Identifiable {
    let idx: Int
    let time: String
    let high: Double
    let low: Double
    let open: Double
    let close: Double

    var id: Int { idx }
    var isUp: Bool { close >= open }
}

/// 分型（顶/底）。
struct Fractal: Codable, Identifiable {
    enum Kind: String, Codable { case top, bottom }
    let type: Kind
    let time: String
    let price: Double
    let idx: Int
    let confirmed: Bool

    var id: String { "\(idx)-\(type.rawValue)" }
}

/// 笔。
struct Stroke: Codable, Identifiable {
    enum Direction: String, Codable { case up, down }
    let direction: Direction
    let startTime: String
    let endTime: String
    let startPrice: Double
    let endPrice: Double
    let high: Double
    let low: Double
    let confirmed: Bool

    var id: String { "\(startTime)-\(endTime)" }

    enum CodingKeys: String, CodingKey {
        case direction, high, low, confirmed
        case startTime = "start_time"
        case endTime = "end_time"
        case startPrice = "start_price"
        case endPrice = "end_price"
    }
}

/// 线段。
struct Segment: Codable, Identifiable {
    enum Direction: String, Codable { case up, down }
    let direction: Direction
    let startTime: String
    let endTime: String
    let startPrice: Double
    let endPrice: Double
    let high: Double
    let low: Double
    let strokeCount: Int
    let confirmed: Bool

    var id: String { "\(startTime)-\(endTime)" }

    enum CodingKeys: String, CodingKey {
        case direction, high, low, confirmed
        case startTime = "start_time"
        case endTime = "end_time"
        case startPrice = "start_price"
        case endPrice = "end_price"
        case strokeCount = "stroke_count"
    }
}

/// 中枢。
struct Pivot: Codable, Identifiable {
    enum Level: String, Codable { case stroke, segment }
    let zg: Double
    let zd: Double
    let gg: Double
    let dd: Double
    let startTime: String
    let endTime: String
    let level: Level
    let confirmed: Bool

    var id: String { "\(level.rawValue)-\(startTime)-\(endTime)" }

    enum CodingKeys: String, CodingKey {
        case zg, zd, gg, dd, level, confirmed
        case startTime = "start_time"
        case endTime = "end_time"
    }
}

/// MACD（DIF/DEA/柱）。
struct MACDData: Codable {
    let times: [String]
    let dif: [Double]
    let dea: [Double]
    let bar: [Double]
}

/// 买卖点信号。
struct Signal: Codable, Identifiable {
    enum Kind: String, Codable {
        case buy1, buy2, buy3, sell1, sell2, sell3
    }
    enum Strength: String, Codable { case strong, medium, weak }

    let type: Kind
    let label: String
    let time: String
    let price: Double
    let strength: Strength
    let isBuy: Bool
    let description: String
    let areaRatio: Double?
    let confirmed: Bool

    var id: String { "\(type.rawValue)-\(time)" }

    enum CodingKeys: String, CodingKey {
        case type, label, time, price, strength, description, confirmed
        case isBuy = "is_buy"
        case areaRatio = "area_ratio"
    }
}

/// 操作建议（含免责边界）。
struct Recommendation: Codable {
    let action: String
    let actionLabel: String
    let bias: String        // bullish / bearish / neutral
    let reasons: [String]
    let caveats: [String]

    enum CodingKeys: String, CodingKey {
        case action, bias, reasons, caveats
        case actionLabel = "action_label"
    }
}

/// 完整缠论分析结果。
struct ChanAnalysis: Codable {
    let symbol: String
    let barsCount: Int
    let mergedCandles: [MergedCandle]
    let fractals: [Fractal]
    let strokes: [Stroke]
    let segments: [Segment]
    let strokePivots: [Pivot]
    let segmentPivots: [Pivot]
    let macd: MACDData?
    let signals: [Signal]
    let currentTrend: String
    let summary: String
    let recommendation: Recommendation?
    let pendingNotes: [String]

    enum CodingKeys: String, CodingKey {
        case symbol, fractals, strokes, segments, macd, signals, summary, recommendation
        case barsCount = "bars_count"
        case mergedCandles = "merged_candles"
        case strokePivots = "stroke_pivots"
        case segmentPivots = "segment_pivots"
        case currentTrend = "current_trend"
        case pendingNotes = "pending_notes"
    }
}

// MARK: - 结构 GAP 分析（对应 StructureGapResponse / GapJobStatus）

struct GapItem: Codable, Identifiable {
    enum Direction: String, Codable {
        case priceLagsIndustry = "price_lags_industry"
        case priceAheadOfFundamentals = "price_ahead_of_fundamentals"
        case unclear
    }
    let dimension: String
    let marketSays: String
    let industrySays: String
    let direction: Direction
    let interpretation: String

    var id: String { dimension }

    enum CodingKeys: String, CodingKey {
        case dimension, direction, interpretation
        case marketSays = "market_says"
        case industrySays = "industry_says"
    }
}

struct StructureGapResult: Codable {
    let symbol: String
    let aligned: [String]
    let gaps: [GapItem]
    let keyQuestion: String
    let caveats: [String]

    enum CodingKeys: String, CodingKey {
        case symbol, aligned, gaps, caveats
        case keyQuestion = "key_question"
    }
}

struct GapJobStatus: Codable {
    enum State: String, Codable { case pending, done, failed }
    let jobId: String
    let status: State
    let result: StructureGapResult?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case status, result, error
        case jobId = "job_id"
    }
}
