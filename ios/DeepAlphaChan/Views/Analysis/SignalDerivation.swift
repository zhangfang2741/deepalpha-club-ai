import SwiftUI

/// 买卖点「怎么识别的」：按严格口径（App 固定口径，见 app/services/chan/signal_policy.py 的 strict）
/// 一步步讲，数字取这个信号自己的真实值。口径变了这里要一起改。
enum SignalDerivation {
    typealias Result = (conclusion: String, steps: [DerivationStep], caveat: String)

    static func build(_ s: Signal) -> Result {
        switch s.type {
        case .buy1, .sell1: return first(s)
        case .buy2, .sell2: return second(s)
        case .buy3, .sell3: return third(s)
        }
    }

    private static func percent(_ v: Double?) -> String {
        v.map { String(format: "%.0f%%", $0 * 100) } ?? "—"
    }

    // MARK: - 一类：趋势背驰

    private static func first(_ s: Signal) -> Result {
        let buy = s.isBuy
        let steps = [
            DerivationStep(
                title: L("先要有趋势"),
                text: buy ? L("价格先走出至少两个依次下移、互不重叠的中枢（A 和 B），并已向下离开 B。")
                          : L("价格先走出至少两个依次上移、互不重叠的中枢（A 和 B），并已向上离开 B。")),
            DerivationStep(
                title: L("再比 b、c 两段的力度"),
                text: L("b 段 = A 与 B 之间的那一段，c 段 = 离开 B 的这一段。各自把 MACD 红绿柱的面积相加，再用 c 段除以 b 段。"),
                values: [(L("面积比（c ÷ b）"), percent(s.areaRatio)),
                         (L("时长比"), percent(s.lengthRatio)),
                         (L("价差比"), percent(s.priceRatio))]),
            DerivationStep(
                title: buy ? L("创新低且面积更小 = 趋势背驰") : L("创新高且面积更小 = 趋势背驰"),
                text: (buy ? L("c 段把价格推到新低，但面积比小于 100%，说明这一段下跌的力气比上一段小，这就是趋势背驰，一类买点成立的条件。")
                           : L("c 段把价格推到新高，但面积比小于 100%，说明这一段上涨的力气比上一段小，这就是趋势背驰，一类卖点成立的条件。"))
                    + L("缠论原文只有「面积更小即背驰」，没有强弱分档，所以强弱统一标「中」。")),
            DerivationStep(
                title: L("走完再确认"),
                text: L("这一笔走完、并且反方向的下一笔已经开始成形，才算成立，所以它比价格转折晚几天出现。后面如果价格继续创新极值，这个一类就作废。")),
        ]
        let head = s.areaRatio.map { L("%@：趋势背驰，面积比 %@", s.label, percent($0)) } ?? L("%@：趋势背驰", s.label)
        return (head, steps,
                L("面积是累计值，c 段常比 b 段短，所以面积比容易偏小，时长比一并列在上面供对照。一类只是背驰迹象，不保证转折，也不是操作建议。"))
    }

    // MARK: - 二类

    private static func second(_ s: Signal) -> Result {
        let buy = s.isBuy
        var steps = [
            DerivationStep(
                title: L("先有同方向的一类"),
                text: buy ? L("二买要建立在一买之上，没有一买就没有二买。") : L("二卖要建立在一卖之上，没有一卖就没有二卖。")),
            DerivationStep(
                title: buy ? L("一买后第一次回落不破一买低点") : L("一卖后第一次反弹不过一卖高点"),
                text: buy ? L("一买之后价格先反弹、再第一次回落，回落的低点没有跌破一买的低点，就是二买。")
                          : L("一卖之后价格先回落、再第一次反弹，反弹的高点没有超过一卖的高点，就是二卖。")),
        ]
        steps.append(strengthStep(s))
        return (L("%@：一类之后的第一次回落 / 反弹没有破极值", s.label), steps,
                L("买卖点只是缠论对价格结构的一次观测，不预测涨跌，也不是操作建议。"))
    }

    // MARK: - 三类

    private static func third(_ s: Signal) -> Result {
        let buy = s.isBuy
        var steps = [
            DerivationStep(
                title: L("先离开中枢"),
                text: buy ? L("价格向上突破中枢区间并离开。") : L("价格向下突破中枢区间并离开。")),
            DerivationStep(
                title: buy ? L("离开后第一次回落没有回到中枢") : L("离开后第一次反弹没有回到中枢"),
                text: buy ? L("回落的低点仍在中枢上沿之上，说明中枢上沿成了支撑，就是三买。")
                          : L("反弹的高点仍在中枢下沿之下，说明中枢下沿成了压力，就是三卖。")),
        ]
        steps.append(strengthStep(s))
        return (L("%@：离开中枢后的第一次回落 / 反弹没有回到中枢", s.label), steps,
                L("买卖点只是缠论对价格结构的一次观测，不预测涨跌，也不是操作建议。"))
    }

    private static func strengthStep(_ s: Signal) -> DerivationStep {
        DerivationStep(
            title: L("强弱怎么定"),
            text: L("看两件事：所靠中枢的级别（笔级、线段级，线段级更强），和回落（反弹）的落点离中枢边界有多远（越远越强）。两项加权后分强 / 中 / 弱。"),
            values: [(L("这个信号"), RadarPanelStyle.strengthText(s.strength.rawValue))])
    }
}
