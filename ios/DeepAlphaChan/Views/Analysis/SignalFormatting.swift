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
}

/// 带标题的项目符号列表。结论段的「依据」和「风险提示」共用。
struct BulletList: View {
    let title: String
    let items: [String]
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption.bold()).foregroundColor(Theme.textSecondary)
            ForEach(items, id: \.self) { item in
                HStack(alignment: .top, spacing: 6) {
                    Text("•").foregroundColor(color)
                    Text(item).font(.caption).foregroundColor(color)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}
