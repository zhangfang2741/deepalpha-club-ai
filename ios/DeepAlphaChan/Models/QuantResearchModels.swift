import Foundation

// 量化研究与分析师评级的接口模型，严格对应后端 app/schemas/quant_research.py 与
// app/schemas/analyst_upgrade.py（AnalystOverviewOut）。文案全部由后端按语言生成，
// 这里只做解码；golden JSON 解码测试见 ios/Tests/QuantResearchTests.swift。

// MARK: - 量化研究

struct QuantResearch: Decodable {
    let market: String
    let symbol: String
    let name: String?
    let status: String              // ok | unsupported_market | insufficient_data
    let statusNote: String?
    let methodologyVersion: String
    let asOf: QuantAsOf?
    let peerGroup: QuantPeerGroup?
    let stage: QuantStage?
    let overall: QuantOverall?
    let dimensions: [QuantDimension]
    let disclaimer: String

    var isOK: Bool { status == "ok" }

    enum CodingKeys: String, CodingKey {
        case market, symbol, name, status, stage, overall, dimensions, disclaimer
        case statusNote = "status_note"
        case methodologyVersion = "methodology_version"
        case asOf = "as_of"
        case peerGroup = "peer_group"
    }
}

struct QuantAsOf: Decodable {
    let priceDate: String?
    let fiscalPeriod: String?
    let filingDate: String?
    let estimatesDate: String?

    enum CodingKeys: String, CodingKey {
        case priceDate = "price_date"
        case fiscalPeriod = "fiscal_period"
        case filingDate = "filing_date"
        case estimatesDate = "estimates_date"
    }
}

struct QuantPeerGroup: Decodable {
    let sectorKey: String
    let sectorName: String
    let sampleSize: Int
    let inUniverse: Bool
    let text: String

    enum CodingKeys: String, CodingKey {
        case text
        case sectorKey = "sector_key"
        case sectorName = "sector_name"
        case sampleSize = "sample_size"
        case inUniverse = "in_universe"
    }
}

struct QuantCashFlows: Decodable {
    let operating: Double
    let investing: Double
    let financing: Double
}

struct QuantStage: Decodable {
    let key: String
    let name: String
    let unprofitable: Bool
    let cashFlows: QuantCashFlows
    let note: String

    enum CodingKeys: String, CodingKey {
        case key, name, unprofitable, note
        case cashFlows = "cash_flows"
    }
}

struct QuantOverall: Decodable {
    let grade: String?
    let score: Double?
    let universePercentile: Double?
    let dimensionsUsed: Int
    let capped: Bool
    let note: String?
    let text: String?

    enum CodingKeys: String, CodingKey {
        case grade, score, capped, note, text
        case universePercentile = "universe_percentile"
        case dimensionsUsed = "dimensions_used"
    }
}

struct QuantKeyFact: Decodable {
    let metric: String
    let text: String
}

struct QuantDimension: Decodable, Identifiable {
    let key: String
    let name: String
    let description: String
    let grade: String?
    let score: Double?
    let status: String              // ok | unavailable | accumulating
    let statusNote: String?
    let isHighest: Bool
    let isLowest: Bool
    let keyFact: QuantKeyFact?
    let formula: String?
    let groups: [QuantMetricGroup]

    var id: String { key }
    var isOK: Bool { status == "ok" }
    var allMetrics: [QuantMetric] { groups.flatMap(\.metrics) }

    enum CodingKeys: String, CodingKey {
        case key, name, description, grade, score, status, formula, groups
        case statusNote = "status_note"
        case isHighest = "is_highest"
        case isLowest = "is_lowest"
        case keyFact = "key_fact"
    }
}

struct QuantMetricGroup: Decodable, Identifiable {
    let name: String
    let metrics: [QuantMetric]
    var id: String { name }
}

struct QuantFormulaInput: Decodable, Identifiable {
    let label: String
    let value: String
    let note: String?
    var id: String { label }
}

struct QuantFormula: Decodable {
    let expression: String
    let inputs: [QuantFormulaInput]
}

struct QuantMetricInterpretation: Decodable, Identifiable {
    let what: String
    let role: String
    let threshold: String
    let calculation: String?
    var id: String { what }
}

struct QuantMetric: Decodable, Identifiable {
    let key: String
    let name: String
    let description: String
    let direction: String           // lower_better | higher_better
    let value: Double?
    let displayValue: String
    let status: String              // ok | not_meaningful | not_applicable | missing | insufficient_sample
    let statusNote: String?
    let percentile: Double?
    let grade: String?
    let sectorMedian: Double?
    let sectorMedianDisplay: String?
    let diffToMedianPct: Double?
    let distribution: [String: Double]?
    let formula: QuantFormula?
    let positionText: String?
    let interpretation: QuantMetricInterpretation?

    var id: String { key }
    var lowerBetter: Bool { direction == "lower_better" }

    enum CodingKeys: String, CodingKey {
        case key, name, description, direction, value, status, percentile, grade, distribution, formula
        case displayValue = "display_value"
        case statusNote = "status_note"
        case sectorMedian = "sector_median"
        case sectorMedianDisplay = "sector_median_display"
        case diffToMedianPct = "diff_to_median_pct"
        case positionText = "position_text"
        case interpretation
    }
}

// MARK: - 方法说明

struct QuantMethodology: Decodable {
    struct Section: Decodable, Identifiable {
        let title: String
        let body: String
        var id: String { title }
    }

    struct Band: Decodable, Identifiable {
        let grade: String
        let minPercentile: Double
        var id: String { grade }
        enum CodingKeys: String, CodingKey {
            case grade
            case minPercentile = "min_percentile"
        }
    }

    struct Metric: Decodable, Identifiable {
        let key: String
        let name: String
        let group: String
        let direction: String
        let description: String
        var id: String { key }
    }

    struct Dimension: Decodable, Identifiable {
        let key: String
        let name: String
        let description: String
        let metrics: [Metric]
        var id: String { key }
    }

    let methodologyVersion: String
    let sections: [Section]
    let gradeBands: [Band]
    let dimensions: [Dimension]
    let disclaimer: String

    enum CodingKeys: String, CodingKey {
        case sections, dimensions, disclaimer
        case methodologyVersion = "methodology_version"
        case gradeBands = "grade_bands"
    }
}

// MARK: - 分析师评级

struct AnalystOverview: Decodable {
    struct RatingCounts: Decodable, Identifiable {
        let date: String
        let strongBuy: Int
        let buy: Int
        let hold: Int
        let sell: Int
        let strongSell: Int
        let total: Int
        var id: String { date }
        enum CodingKeys: String, CodingKey {
            case date, buy, hold, sell, total
            case strongBuy = "strong_buy"
            case strongSell = "strong_sell"
        }
    }

    struct Ratings: Decodable {
        let current: RatingCounts?
        let history: [RatingCounts]
        let changeText: String?
        enum CodingKeys: String, CodingKey {
            case current, history
            case changeText = "change_text"
        }
    }

    struct PriceTarget: Decodable {
        let price: Double?
        let high: Double?
        let low: Double?
        let median: Double?
        let consensus: Double?
        let vsPricePct: Double?
        let vsPriceText: String?
        let lastMonthCount: Int?
        let lastQuarterCount: Int?
        let lastYearCount: Int?
        enum CodingKeys: String, CodingKey {
            case price, high, low, median, consensus
            case vsPricePct = "vs_price_pct"
            case vsPriceText = "vs_price_text"
            case lastMonthCount = "last_month_count"
            case lastQuarterCount = "last_quarter_count"
            case lastYearCount = "last_year_count"
        }
    }

    struct Quarter: Decodable, Identifiable {
        let date: String
        let epsActual: Double
        let epsEstimated: Double?
        let surprisePct: Double?
        var id: String { date }
        enum CodingKeys: String, CodingKey {
            case date
            case epsActual = "eps_actual"
            case epsEstimated = "eps_estimated"
            case surprisePct = "surprise_pct"
        }
    }

    struct NextEarnings: Decodable {
        let date: String
        let epsEstimated: Double?
        let revenueEstimated: Double?
        enum CodingKeys: String, CodingKey {
            case date
            case epsEstimated = "eps_estimated"
            case revenueEstimated = "revenue_estimated"
        }
    }

    struct Earnings: Decodable {
        let quarters: [Quarter]
        let next: NextEarnings?
    }

    struct GradeChange: Decodable, Identifiable {
        let date: String
        let firm: String
        let action: String
        let actionLabel: String
        let previousGrade: String?
        let previousGradeLabel: String?
        let newGrade: String
        let newGradeLabel: String
        var id: String { "\(date)-\(firm)-\(newGrade)" }
        enum CodingKeys: String, CodingKey {
            case date, firm, action
            case actionLabel = "action_label"
            case previousGrade = "previous_grade"
            case previousGradeLabel = "previous_grade_label"
            case newGrade = "new_grade"
            case newGradeLabel = "new_grade_label"
        }
    }

    let symbol: String
    let status: String
    let statusNote: String?
    let ratings: Ratings?
    let priceTarget: PriceTarget?
    let earnings: Earnings?
    let recentGrades: [GradeChange]
    let note: String

    var isOK: Bool { status == "ok" }

    enum CodingKeys: String, CodingKey {
        case symbol, status, ratings, earnings, note
        case statusNote = "status_note"
        case priceTarget = "price_target"
        case recentGrades = "recent_grades"
    }
}
