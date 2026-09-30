import Foundation

/// 所选股票池的评级覆盖统计，包含没有技术信号的股票。
struct RadarQuantFilter: Decodable {
    let minGrade: String
    let status: String
    let eligible: Int
    let belowThreshold: Int
    let missing: Int
    let stale: Int
    let maxAgeDays: Int
    let preserveSells: Bool

    enum CodingKeys: String, CodingKey {
        case status, eligible, missing, stale
        case minGrade = "min_grade"
        case belowThreshold = "below_threshold"
        case maxAgeDays = "max_age_days"
        case preserveSells = "preserve_sells"
    }
}
