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
            return L("营收高速增长，但经营活动还没有产生正向现金流，扩张仍靠外部资金或账上存量支撑。营收基数为零、仍在烧钱的公司也归入这里。")
        case .growth:
            return L("营收高速增长，且经营活动已经能产生现金。增长持续性、利润率能否随规模提升是这一阶段的常见观察点。")
        case .mature:
            return L("营收增速平稳，经营活动稳定产生现金。现金多用于分红、回购或再投资，具体去向仍需查看财报。")
        case .shakeout:
            return L("营收在萎缩但经营仍有现金流入，或营收平稳但经营现金流转负。它不一定意味着经营恶化，也不能据此认定正在进入收缩。")
        case .decline:
            return L("营收明显萎缩，且经营活动没有产生正向现金流。是否涉及行业下行、资产处置等情况，需要进一步查看财报。")
        }
    }

    /// 门槛与后端 stage.py 一致（GROWTH_YOY_MIN / GROWTH_CAGR3_MIN / SHRINK_YOY_MAX），由后端 test_stage_ios_rules_match_thresholds 守护。
    var rule: String {
        switch self {
        case .intro: return L("营收同比 ≥ 15% 且 3 年复合 ≥ 10% · 经营现金流 ≤ 0")
        case .growth: return L("营收同比 ≥ 15% 且 3 年复合 ≥ 10% · 经营现金流 > 0")
        case .mature: return L("营收同比在 −5% ~ 15% 之间 · 经营现金流 > 0")
        case .shakeout: return L("营收同比 ≤ −5% · 经营现金流 > 0；或营收同比在 −5% ~ 15% 之间 · 经营现金流 ≤ 0")
        case .decline: return L("营收同比 ≤ −5% · 经营现金流 ≤ 0")
        }
    }

    static func signLabel(_ value: Double) -> String {
        if value > 0 { return L("正值 · 流入") }
        if value < 0 { return L("负值 · 流出") }
        return L("零值 · 按非正值处理")
    }
}
