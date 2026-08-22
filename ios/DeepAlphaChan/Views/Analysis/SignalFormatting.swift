import SwiftUI

/// 分析结果的文案与配色映射。
///
/// 从 SignalPanelView 抽出来：结论段和买卖点段拆开后，两边都要用这套映射，
/// 留在任何一边都会让另一边去引用一个「看起来不相干」的视图。
enum SignalFormatting {

    static func trendLabel(_ trend: String) -> String {
        switch trend {
        case "up": return "上涨趋势"
        case "down": return "下跌趋势"
        case "oscillation", "range": return "震荡整理"
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
        case "bullish": return "偏多"
        case "bearish": return "偏空"
        default: return "中性"
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
        case .strong: return "强"
        case .medium: return "中"
        case .weak: return "弱"
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
}

/// 结论区统一的字号层级。
///
/// 改造前这块混用了 12/13/15/20 四种字号，而且「依据」这类小标题(12pt)比它
/// 统领的正文(13pt)还小，层级是倒的。现在收成三级：
///
/// - 卡片标题 17pt semibold（SectionCard 自带）
/// - 正文 15pt regular，行距 5——这是真正要读的内容，不该比标题挤
/// - 段内小标题 13pt semibold + 字距，小而重才像标签而不像正文
enum ConclusionType {
    static let body = Font.system(size: 15)
    static let label = Font.system(size: 13, weight: .semibold)
    static let bodyLineSpacing: CGFloat = 5
}

/// 带标题的项目符号列表。结论段的「依据」和「风险提示」共用。
struct BulletList: View {
    let title: String
    let items: [String]
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(title)
                .font(ConclusionType.label)
                .tracking(0.5)
                .foregroundColor(Theme.textSecondary)

            ForEach(items, id: \.self) { item in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    // 圆点比正文暗一档并固定宽度，多行时缩进才对得齐
                    Circle()
                        .fill(color.opacity(0.55))
                        .frame(width: 4, height: 4)
                        .frame(width: 6, alignment: .center)
                        .offset(y: -4)
                    Text(item)
                        .font(ConclusionType.body)
                        .foregroundColor(color)
                        .lineSpacing(ConclusionType.bodyLineSpacing)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}
