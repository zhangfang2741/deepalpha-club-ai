import SwiftUI

/// 五个维度的大白话：一句话问题 + 一段「这个维度看什么」，以及首页 / 详情共用的等级读法。
enum QuantDimensionGuide {
    static func question(_ key: String) -> String? {
        switch key {
        case "profitability": return L("赚钱能力如何")
        case "growth": return L("生意是否在成长")
        case "valuation": return L("价格相对基本面如何")
        case "momentum": return L("市场近期如何定价")
        case "revisions": return L("盈利预期有何变化")
        default: return nil
        }
    }

    static func intro(_ key: String) -> String? {
        switch key {
        case "profitability":
            return L("看公司做生意的效率：每卖 100 元能留下多少利润和现金，股东和债主投进去的钱一年能赚回多少。")
        case "growth":
            return L("看生意有没有变大：营收、经营利润、每股收益比之前多了多少，以及分析师预计未来还能长多少。")
        case "valuation":
            return L("看价格贵不贵：买下这家公司，相当于付了几年的利润、营收或现金流。倍数越低，排名越靠前。")
        case "momentum":
            return L("看市场最近怎么给它定价：过去 3 到 12 个月股价涨跌了多少。它反映市场情绪，不代表公司本身变好。")
        case "revisions":
            return L("看专业人士的态度变化：分析师对未来业绩的平均预测，最近是上调还是下调。")
        default:
            return nil
        }
    }

    /// 等级读法：等级是同板块里的相对位置，不是绝对好坏。
    static var gradeReading: String {
        L("等级是和同板块公司比出来的相对位置：A 档约前 20%，C 档居中，F 档约后 20%。")
    }
}
