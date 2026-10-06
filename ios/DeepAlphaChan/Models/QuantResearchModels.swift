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
    /// 护城河（Morningstar 框架：宽 / 窄 / 无）；旧响应没有此字段。
    let moat: QuantMoat?
    let disclaimer: String

    var isOK: Bool { status == "ok" }

    enum CodingKeys: String, CodingKey {
        case market, symbol, name, status, stage, overall, dimensions, disclaimer, moat
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
    /// 港股：财务数据与预期折成港元时的汇率说明
    let currencyNote: String?

    enum CodingKeys: String, CodingKey {
        case priceDate = "price_date"
        case fiscalPeriod = "fiscal_period"
        case filingDate = "filing_date"
        case estimatesDate = "estimates_date"
        case currencyNote = "currency_note"
    }
}

struct QuantPeerGroup: Decodable {
    let sectorKey: String
    let sectorName: String
    let sampleSize: Int
    let inUniverse: Bool
    let text: String
    /// 比较样本的叫法（标普1500 / A 股市值前 1800 / 港股通及大中型港股）；旧接口没有，按美股处理
    let universeName: String?

    enum CodingKeys: String, CodingKey {
        case text
        case sectorKey = "sector_key"
        case sectorName = "sector_name"
        case sampleSize = "sample_size"
        case inUniverse = "in_universe"
        case universeName = "universe_name"
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
    /// false = 只展示、不计入综合等级（护城河）；旧响应缺省为 true。
    let countsInOverall: Bool

    var id: String { key }
    var isOK: Bool { status == "ok" }
    var allMetrics: [QuantMetric] { groups.flatMap(\.metrics) }

    enum CodingKeys: String, CodingKey {
        case key, name, description, grade, score, status, formula, groups
        case statusNote = "status_note"
        case isHighest = "is_highest"
        case isLowest = "is_lowest"
        case keyFact = "key_fact"
        case countsInOverall = "counts_in_overall"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        key = try c.decode(String.self, forKey: .key)
        name = try c.decode(String.self, forKey: .name)
        description = try c.decode(String.self, forKey: .description)
        grade = try c.decodeIfPresent(String.self, forKey: .grade)
        score = try c.decodeIfPresent(Double.self, forKey: .score)
        status = try c.decode(String.self, forKey: .status)
        statusNote = try c.decodeIfPresent(String.self, forKey: .statusNote)
        isHighest = try c.decode(Bool.self, forKey: .isHighest)
        isLowest = try c.decode(Bool.self, forKey: .isLowest)
        keyFact = try c.decodeIfPresent(QuantKeyFact.self, forKey: .keyFact)
        formula = try c.decodeIfPresent(String.self, forKey: .formula)
        groups = try c.decode([QuantMetricGroup].self, forKey: .groups)
        countsInOverall = try c.decodeIfPresent(Bool.self, forKey: .countsInOverall) ?? true
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
    /// 计入综合等级的维度（五维成绩单、五维图、综合分解释）。
    var scoredDimensions: [QuantDimension] { dimensions.filter(\.countsInOverall) }

}

// MARK: - 护城河

struct QuantMoatYear: Decodable, Identifiable {
    let year: Int
    let value: Double
    var id: Int { year }
}

struct QuantMoatEvidence: Decodable {
    let metric: String              // roic | roe
    let metricName: String
    let years: [QuantMoatYear]      // 新 → 旧
    let costOfCapital: Double
    let yearsAbove: Int
    let nYears: Int
    let avgSpread: Double?
    let level: String               // strong | moderate | weak
    let levelName: String
    let text: String

    enum CodingKeys: String, CodingKey {
        case metric, years, level, text
        case metricName = "metric_name"
        case costOfCapital = "cost_of_capital"
        case yearsAbove = "years_above"
        case nYears = "n_years"
        case avgSpread = "avg_spread"
        case levelName = "level_name"
    }
}

struct QuantMoatSource: Decodable, Identifiable {
    let key: String
    let name: String
    let strength: String            // none | weak | moderate | strong
    let strengthName: String
    let reason: String
    let quotes: [String]
    var id: String { key }

    /// 强度对应的实心点数（0 ~ 3）。
    var dots: Int { ["none", "weak", "moderate", "strong"].firstIndex(of: strength) ?? 0 }

    enum CodingKeys: String, CodingKey {
        case key, name, strength, reason, quotes
        case strengthName = "strength_name"
    }
}

struct QuantMoat: Decodable {
    let status: String              // ok | pending | not_covered
    let statusNote: String?
    let rating: String?             // wide | narrow | none
    let ratingName: String?
    let trend: String?              // widening | stable | narrowing
    let trendName: String?
    let summary: String?
    let evidence: QuantMoatEvidence?
    let sources: [QuantMoatSource]
    let threats: String?
    let filedDate: String?
    let tenkUrl: String?
    let methodNote: String

    var isOK: Bool { status == "ok" && rating != nil }

    enum CodingKeys: String, CodingKey {
        case status, rating, trend, summary, evidence, sources, threats
        case statusNote = "status_note"
        case ratingName = "rating_name"
        case trendName = "trend_name"
        case filedDate = "filed_date"
        case tenkUrl = "tenk_url"
        case methodNote = "method_note"
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
        /// 五档名称（A 股 / 港股：买入 / 增持 / 中性 / 减持 / 卖出）；美股为空，用默认档位
        let bucketLabels: [String]?
        enum CodingKeys: String, CodingKey {
            case current, history
            case changeText = "change_text"
            case bucketLabels = "bucket_labels"
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
        let priceTarget: Double?
        /// 研报标题 / 原文链接（仅 A 股有）
        let reportTitle: String?
        let reportUrl: String?
        /// report = 研报原文 PDF；news = 相关新闻报道（美股）
        let reportKind: String?
        var id: String { "\(date)-\(firm)-\(newGrade)" }
        enum CodingKeys: String, CodingKey {
            case date, firm, action
            case actionLabel = "action_label"
            case previousGrade = "previous_grade"
            case previousGradeLabel = "previous_grade_label"
            case newGrade = "new_grade"
            case newGradeLabel = "new_grade_label"
            case priceTarget = "price_target"
            case reportTitle = "report_title"
            case reportUrl = "report_url"
            case reportKind = "report_kind"
        }
    }

    let symbol: String
    let status: String
    let statusNote: String?
    let ratings: Ratings?
    let priceTarget: PriceTarget?
    let earnings: Earnings?
    let recentGrades: [GradeChange]
    /// 港股只有各券商最新评级时给出（「各券商最新评级」）
    let recentGradesTitle: String?
    let note: String

    var isOK: Bool { status == "ok" }

    enum CodingKeys: String, CodingKey {
        case symbol, status, ratings, earnings, note
        case statusNote = "status_note"
        case priceTarget = "price_target"
        case recentGrades = "recent_grades"
        case recentGradesTitle = "recent_grades_title"
    }
}


/// 最新一份定期财报的位置（美股是 SEC 网页文档，A 股 / 港股是 PDF）。
struct LatestReport: Decodable {
    let status: String
    let symbol: String
    let title: String?
    let reportType: String?
    let period: String?
    let filedDate: String?
    let url: String?
    let fileType: String?

    var isOK: Bool { status == "ok" && url != nil }

    enum CodingKeys: String, CodingKey {
        case status, symbol, title, period, url
        case reportType = "report_type"
        case filedDate = "filed_date"
        case fileType = "file_type"
    }
}
