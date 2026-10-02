import Foundation

/// 市场状态（资金流向口径）与恐慌贪婪（整体情绪口径）方向相反时给的一句说明。
/// 纯函数，只描述环境，不出现买卖导向词；返回 nil 表示两者不矛盾、不显示。
enum MacroConsistency {
    /// 情绪分低于它算「偏恐慌」（与恐慌贪婪的「恐慌」档上沿一致）。
    static let fearBelow = 45.0
    /// 情绪分高于它算「偏贪婪」。
    static let greedAbove = 55.0

    enum Kind: Equatable {
        /// 逐利 + 情绪偏恐慌：下跌后的修复初期
        case riskOnButFear
        /// 避险 + 情绪偏贪婪：上涨后的降温初期
        case riskOffButGreed
    }

    static func kind(label: String, score: Double) -> Kind? {
        switch label {
        case "risk_on" where score < fearBelow: return .riskOnButFear
        case "risk_off" where score > greedAbove: return .riskOffButGreed
        default: return nil
        }
    }
}
