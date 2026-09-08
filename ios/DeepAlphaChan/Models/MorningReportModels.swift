import Foundation

/// 晨报后端 JSON 映射。`MR` 前缀 = Morning Report，避免与缠论模型混淆。
///
/// 双语为叶子级 LocalizedText：zh 必有，en 可能缺（旧数据兜底），`resolved` 做回退。
struct LocalizedText: Decodable, Hashable {
    let zh: String
    let en: String?

    /// 按当前 App 语言取文案；en 为空回退 zh。
    var resolved: String {
        Localized.language() == .english ? (en?.isEmpty == false ? en! : zh) : zh
    }
}

struct MRMetric: Decodable, Hashable {
    let name: LocalizedText
    let value: String
    let direction: String   // up / down / flat
    let note: LocalizedText
}

struct MRSectionEntry: Decodable, Hashable {
    let fact: LocalizedText
    let insight: LocalizedText
    let prediction: LocalizedText
    let verification: LocalizedText
}

struct MRSection: Decodable, Hashable {
    let key: String          // pricing_gap / earnings_valuation / industry_chain / crowding_risk
    let title: LocalizedText
    let entries: [MRSectionEntry]
}

struct MRStockPick: Decodable, Hashable {
    let symbol: String
    let name: LocalizedText
    let changePct: String
    let direction: String
    let bull: LocalizedText
    let base: LocalizedText
    let bear: LocalizedText

    enum CodingKeys: String, CodingKey {
        case symbol, name, direction, bull, base, bear
        case changePct = "change_pct"
    }
}

struct MRCatalyst: Decodable, Hashable {
    let date: String         // YYYY-MM-DD
    let event: LocalizedText
    let why: LocalizedText
    let market: String       // us / cn / hk
}

struct MorningReportContent: Decodable, Hashable {
    let headline: LocalizedText
    let summary: LocalizedText
    let metrics: [MRMetric]
    let sections: [MRSection]
    let stocks: [MRStockPick]
    let catalysts: [MRCatalyst]
}

struct MorningReportMeta: Decodable, Hashable {
    let market: String
    let tradeDate: String?
    let status: String       // success / generating / pending / empty
    let stale: Bool

    enum CodingKeys: String, CodingKey {
        case market, status, stale
        case tradeDate = "trade_date"
    }
}

struct MorningReportResponse: Decodable {
    let meta: MorningReportMeta
    let content: MorningReportContent?
}

struct ReportDatesResponse: Decodable {
    let market: String
    let dates: [String]
}

struct AckResponse: Decodable {
    let ok: Bool
}
