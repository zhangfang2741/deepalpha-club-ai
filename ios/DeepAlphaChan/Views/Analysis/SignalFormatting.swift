import SwiftUI

/// 分析结果的文案与配色映射。
///
/// 从 SignalPanelView 抽出来：形态分析段和买卖点段拆开后，两边都要用这套映射，
/// 留在任何一边都会让另一边去引用一个「看起来不相干」的视图。
enum SignalFormatting {

    static func trendLabel(_ trend: String) -> String {
        switch trend {
        case "up": return L("上涨趋势")
        case "down": return L("下跌趋势")
        case "oscillation", "range": return L("震荡整理")
        default: return trend
        }
    }

    static func trendColor(_ trend: String) -> Color {
        switch trend {
        case "up": return Theme.up
        case "down": return Theme.down
        default: return Theme.segment
        }
    }

    static func biasLabel(_ bias: String) -> String {
        switch bias {
        case "bullish": return L("偏多")
        case "bearish": return L("偏空")
        default: return L("中性")
        }
    }

    static func biasColor(_ bias: String) -> Color {
        switch bias {
        case "bullish": return Theme.up
        case "bearish": return Theme.down
        default: return Theme.segment
        }
    }

    static func strengthLabel(_ strength: Signal.Strength) -> String {
        switch strength {
        case .strong: return L("强")
        case .medium: return L("中")
        case .weak: return L("弱")
        }
    }

    static func strengthColor(_ strength: Signal.Strength) -> Color {
        switch strength {
        case .strong: return Theme.accent
        case .medium: return Theme.segment
        case .weak: return Theme.textSecondary
        }
    }

    /// 形态阶段的配色：偏多用涨色、偏空用跌色、需警惕/中性用橙色。
    static func phaseColor(_ phase: String) -> Color {
        switch phase {
        case "breakout", "uptrend", "range_strong": return Theme.up
        case "breakdown", "downtrend": return Theme.down
        default: return Theme.segment  // topping / bottoming / range / unclear：警示或中性
        }
    }

    // MARK: - 走势类型 / 走势展望（对应后端 walk_type / trend_outlook）
    //
    // 后端把这两个字段以 raw code 下发（app/services/chan/analyzer.py 里有对应的
    // _walk_type_label / _trend_outlook_label 长句版），这里给一套「短标签 + 配色」
    // 的映射供整体分析卡当 chip 用。走势类型是缠论按**中枢排布**定义的大级别走势，
    // trend_outlook 由 walk_type + 终结性背驰派生，两者天然自洽、不会互相打架。

    /// 走势类型短标签（基于中枢排布）。
    static func walkTypeLabel(_ walkType: String?) -> String {
        switch walkType ?? "" {
        case "up_trend": return L("上涨趋势")
        case "down_trend": return L("下跌趋势")
        case "consolidation": return L("盘整")
        default: return L("趋势未成形")
        }
    }

    /// 走势类型的一句补充说明（中枢怎么排布出来的）。
    static func walkTypeDetail(_ walkType: String?) -> String {
        switch walkType ?? "" {
        case "up_trend": return L("中枢依次抬高")
        case "down_trend": return L("中枢依次降低")
        case "consolidation": return L("围绕中枢震荡")
        default: return L("单边推进或数据不足，尚未形成中枢")
        }
    }

    static func walkTypeColor(_ walkType: String?) -> Color {
        switch walkType ?? "" {
        case "up_trend": return Theme.up
        case "down_trend": return Theme.down
        default: return Theme.segment
        }
    }

    /// 走势展望短标签（延续 vs 转折 vs 盘整突破）。
    static func trendOutlookLabel(_ outlook: String?) -> String {
        switch outlook ?? "" {
        case "reversal_up": return L("可能转折向上")
        case "reversal_down": return L("可能转折向下")
        case "continuation_up": return L("上涨延续")
        case "continuation_down": return L("下跌延续")
        case "breakout_up": return L("盘整上破")
        case "breakout_down": return L("盘整下破")
        case "range": return L("盘整延续")
        default: return L("展望未明")
        }
    }

    static func trendOutlookColor(_ outlook: String?) -> Color {
        switch outlook ?? "" {
        case "reversal_up", "continuation_up", "breakout_up": return Theme.up
        case "reversal_down", "continuation_down", "breakout_down": return Theme.down
        default: return Theme.segment
        }
    }
}

/// 分析区统一的字号层级。
///
/// 改造前这块混用了 12/13/15/20 四种字号，而且「依据」这类小标题(12pt)比它
/// 统领的正文(13pt)还小，层级是倒的。现在收成三级：
///
/// - 卡片标题 17pt semibold（SectionCard 自带）
/// - 正文 15pt regular，行距 5——这是真正要读的内容，不该比标题挤
/// - 段内小标题 13pt semibold + 字距，小而重才像标签而不像正文
enum AnalysisType {
    // 用文本样式而不是固定 size：.system(size:) 不跟随系统的「文字大小」设置，
    // 调大字号的用户看到的还是 15pt。subheadline 本身就是 15pt，footnote 13pt，
    // 视觉不变但会随动态字体缩放。
    static let body = Font.subheadline
    static let label = Font.footnote.weight(.semibold)
    static let bodyLineSpacing: CGFloat = 5
}

/// 项目符号列表。标题可省——风险提示自己就是一张卡，卡标题之下再来个同名
/// 小标题只是重复。
struct BulletList: View {
    var title: String? = nil
    let items: [String]
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            if let title {
                Text(title)
                    .font(AnalysisType.label)
                    .tracking(0.5)
                    .foregroundColor(Theme.textSecondary)
            }

            ForEach(items, id: \.self) { item in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    // 圆点比正文暗一档并固定宽度，多行时缩进才对得齐
                    Circle()
                        .fill(color.opacity(0.55))
                        .frame(width: 4, height: 4)
                        .frame(width: 6, alignment: .center)
                        .offset(y: -4)
                    Text(item)
                        .font(AnalysisType.body)
                        .foregroundColor(color)
                        .lineSpacing(AnalysisType.bodyLineSpacing)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}
