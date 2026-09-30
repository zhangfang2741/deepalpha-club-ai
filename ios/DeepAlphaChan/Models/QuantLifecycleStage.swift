import Foundation

/// 展示顺序与后端阶段键对应；阶段位置表示分类，不表示完成比例。
enum QuantLifecycleStage: String, CaseIterable, Identifiable {
    case intro, growth, mature, shakeout, decline

    var id: String { rawValue }

    var title: String {
        switch self {
        case .intro: return L("初创期")
        case .growth: return L("成长期")
        case .mature: return L("成熟期")
        case .shakeout: return L("调整期")
        case .decline: return L("收缩期")
        }
    }

    var shortTitle: String {
        switch self {
        case .intro: return L("初创")
        case .growth: return L("成长")
        case .mature: return L("成熟")
        case .shakeout: return L("调整")
        case .decline: return L("收缩")
        }
    }

    var explanation: String {
        switch self {
        case .intro:
            return L("经营与投资现金流均为净流出或零，同时筹资带来现金流入。本页将这种现金流结构标为初创期，不代表公司一定刚成立。")
        case .growth:
            return L("经营活动产生现金，投资现金流为净流出或零，同时筹资带来现金流入。本页将这种结构标为成长期。")
        case .mature:
            return L("经营活动产生现金，投资与筹资活动均为净流出或零。本页将这种结构标为成熟期；筹资流出可能涉及还债、分红或回购，具体原因仍需查看财报。")
        case .shakeout:
            return L("现金流组合未落入初创、成长、成熟或收缩规则，本页归为调整期。它不一定意味着经营恶化，也不能据此认定正在进入收缩。")
        case .decline:
            return L("经营活动未产生正向净现金流，而投资活动带来现金流入。本页将这种结构标为收缩期；是否涉及资产处置等情况，需要进一步查看财报。")
        }
    }

    var rule: String {
        switch self {
        case .intro: return L("经营 ≤ 0 · 投资 ≤ 0 · 筹资 > 0")
        case .growth: return L("经营 > 0 · 投资 ≤ 0 · 筹资 > 0")
        case .mature: return L("经营 > 0 · 投资 ≤ 0 · 筹资 ≤ 0")
        case .shakeout: return L("经营 > 0、投资 > 0（筹资不限）；或三项均 ≤ 0。")
        case .decline: return L("经营 ≤ 0 · 投资 > 0 · 筹资不限")
        }
    }

    static func signLabel(_ value: Double) -> String {
        if value > 0 { return L("正值 · 流入") }
        if value < 0 { return L("负值 · 流出") }
        return L("零值 · 按非正值处理")
    }
}
