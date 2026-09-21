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

/// 大白话形态解读（对应后端 MarketNarrativeOut）。
struct MarketNarrative: Codable {
    let phase: String          // 阶段代码
    let phaseLabel: String     // 阶段中文标签
    let headline: String       // 一句话形态概括
    let details: [String]      // 分条解读（趋势 / 位置 / 量价 / 动能）

    enum CodingKeys: String, CodingKey {
        case phase, headline, details
        case phaseLabel = "phase_label"
    }
}

/// 中枢生命周期 checklist 里的一行（对应后端 PhaseChecklistItemOut）。
struct PhaseChecklistItem: Codable, Identifiable {
    enum State: String, Codable { case done, pending }
    let label: String
    let detail: String
    let state: State

    // label 目前唯一：后端 pivot_phase.py 的 _checklist() 每次最多生成 3 条不同文案，
    // 唯一性是隐式约定，不是类型层面保证的，后端改动时留意别引入重复 label。
    var id: String { label }
}

/// 回抽结果的一种可能分支（对应后端 PhaseBranchOut，仅 leaving 阶段非空）。
struct PhaseBranch: Codable, Identifiable {
    let outcome: String  // type2 / type3 / back_to_range
    let conditionLabel: String
    let resultLabel: String

    // outcome 目前唯一：后端 pivot_phase.py 的 _branches() 固定只产出 type2/type3/
    // back_to_range 这 3 个 outcome，唯一性由后端实现保证，不是类型层面保证的。
    var id: String { outcome }

    enum CodingKeys: String, CodingKey {
        case outcome
        case conditionLabel = "condition_label"
        case resultLabel = "result_label"
    }
}

/// 阶段讲解弹层里的一个标准步骤（对应后端 StageGuideStepOut）。
struct StageGuideStep: Codable, Identifiable {
    let key: String
    let title: String
    let detail: String

    // key 目前唯一：后端 pivot_phase.py 的 _stage_guide() 固定产出同一组 5 个阶段 key，
    // 唯一性是隐式约定，不是类型层面保证的。
    var id: String { key }
}

/// 阶段讲解弹层内容（对应后端 StageGuideOut）。
struct StageGuide: Codable {
    let currentIndex: Int
    let steps: [StageGuideStep]
    let whyItMatters: String

    enum CodingKeys: String, CodingKey {
        case steps
        case currentIndex = "current_index"
        case whyItMatters = "why_it_matters"
    }
}

/// 中枢生命周期状态机：「走到哪一步」（对应后端 PivotPhaseOut）。
struct PivotPhase: Codable {
    let phase: String  // pivot_forming / pivot_oscillating / leaving / retrace_confirmed / divergence_turn
    let phaseLabel: String
    let direction: String?  // up / down / nil
    let pivot: Pivot
    let checklist: [PhaseChecklistItem]
    let reason: String
    let confirmed: Bool
    let branches: [PhaseBranch]
    let stageGuide: StageGuide

    enum CodingKeys: String, CodingKey {
        case phase, pivot, checklist, reason, confirmed, branches, direction
        case phaseLabel = "phase_label"
        case stageGuide = "stage_guide"
    }
}

/// 结构分层判断依据的一条：笔/线段/中枢/买卖点各自的当前状态
/// （对应后端 StructureLayerOut）。
struct StructureLayer: Codable, Identifiable {
    let layer: String  // stroke / segment / pivot / signal
    let label: String
    let title: String
    let detail: String

    var id: String { layer }
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
    // 走势类型（基于中枢排布）：up_trend / down_trend / consolidation / none
    let walkType: String?
    let walkTypeLabel: String?
    // 走势展望（延续 vs 转折）：reversal_up / reversal_down / continuation_up /
    // continuation_down / breakout_up / breakout_down / range / unclear
    let trendOutlook: String?
    let trendOutlookLabel: String?
    let summary: String
    let recommendation: Recommendation?
    let narrative: MarketNarrative?
    let pendingNotes: [String]
    let pivotPhase: PivotPhase?
    let structureLayers: [StructureLayer]
    let structureHeadline: String?

    enum CodingKeys: String, CodingKey {
        case symbol, fractals, strokes, segments, macd, signals, summary, recommendation, narrative
        case barsCount = "bars_count"
        case mergedCandles = "merged_candles"
        case strokePivots = "stroke_pivots"
        case segmentPivots = "segment_pivots"
        case currentTrend = "current_trend"
        case walkType = "walk_type"
        case walkTypeLabel = "walk_type_label"
        case trendOutlook = "trend_outlook"
        case trendOutlookLabel = "trend_outlook_label"
        case pendingNotes = "pending_notes"
        case pivotPhase = "pivot_phase"
        case structureLayers = "structure_layers"
        case structureHeadline = "structure_headline"
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
