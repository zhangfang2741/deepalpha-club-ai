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
    let revenueGrowthPct: Double?
    let revenueCagr3yPct: Double?

    enum CodingKeys: String, CodingKey {
        case key, name, unprofitable, note
        case cashFlows = "cash_flows"
        case revenueGrowthPct = "revenue_growth_pct"
        case revenueCagr3yPct = "revenue_cagr_3y_pct"
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
    /// 大白话：这个输入是什么、取的哪个期间；旧缓存响应可能缺失。
    let hint: String?
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
    /// 大白话三段（全称 / 日常语言释义 / 高低怎么看）；旧缓存响应可能缺失。
    let fullName: String?
    let plain: String?
    let reading: String?
    /// 为什么重要 / 我们为什么用它（在评级里的作用）；旧缓存响应可能缺失。
    let why: String?
    let purpose: String?
    var id: String { what }

    enum CodingKeys: String, CodingKey {
        case what, role, threshold, calculation, plain, reading, why, purpose
        case fullName = "full_name"
    }
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

    /// 全称副标题：只在它补充了信息时返回（如「ROE」→「净资产收益率 ROE…」）；
    /// 去掉期间修饰后名称已是全称开头（「毛利率」「前瞻市盈率」）则不重复显示。
    var fullNameSubtitle: String? {
        guard let full = interpretation?.fullName, !full.isEmpty else { return nil }
        var core = name
        for token in ["前瞻", " TTM", " (TTM)", " (FWD)"] { core = core.replacingOccurrences(of: token, with: "") }
        core = core.trimmingCharacters(in: .whitespaces)
        return full.lowercased().hasPrefix(core.lowercased()) ? nil : full
    }

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

extension QuantResearch {
    /// 首页摘要的「强项 / 短板」：A 档（板块约前 20%）为强项，D / F 档为短板，按维度分高低排序。
    var strengths: [QuantDimension] {
        dimensions.filter { $0.isOK && $0.grade?.first == "A" }
            .sorted { ($0.score ?? 0) > ($1.score ?? 0) }
    }

    var weaknesses: [QuantDimension] {
        dimensions.filter { $0.isOK && ($0.grade?.first == "D" || $0.grade?.first == "F") }
            .sorted { ($0.score ?? 0) < ($1.score ?? 0) }
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
