import SwiftUI

/// 分析结果的文案与配色映射。
///
/// 从 SignalPanelView 抽出来：形态分析段和买卖点段拆开后，两边都要用这套映射，
/// 留在任何一边都会让另一边去引用一个「看起来不相干」的视图。
enum SignalFormatting {

    /// 与雷达共用：强弱只控制红／绿的深浅，不改成蓝／橙等类别色。
    static func strengthDepth(_ strength: String) -> Double {
        switch strength {
        case "strong": return 0.9
        case "weak": return 0.2
        default: return 0.55
        }
    }

    static func radarColor(side: String, depth: Double) -> Color {
        let t = min(max(depth, 0), 1)
        func lerp(_ a: Double, _ b: Double) -> Double { a + (b - a) * t }
        if side == "buy" {
            return Color(.sRGB,
                         red: lerp(248, 120) / 255, green: lerp(113, 15) / 255, blue: lerp(133, 38) / 255)
        }
        return Color(.sRGB,
                     red: lerp(110, 4) / 255, green: lerp(231, 90) / 255, blue: lerp(183, 64) / 255)
    }

    static func typeExplanation(_ kind: Signal.Kind) -> String {
        switch kind {
        case .buy1, .sell1:
            return L("一类观察创新低／新高时的力度衰竭。强度按价差比分档：小于 0.6 为强，0.6 至小于 0.8 为中，其余为弱。")
        case .buy2, .sell2:
            return L("二类观察回调／反弹是否获得支撑或压力。本 App 结合回调笔长度和此前多次转折的重叠区间识别，具体依据见上方说明与学习词条。")
        case .buy3, .sell3:
            return L("三类观察离开中枢后的回抽是否留在中枢之外。本 App 还核对相关笔与均线条件，仅越过中枢边界不足以确认信号。")
        }
    }

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

    /// 形态阶段的配色：偏多用涨色、偏空用跌色、需警惕/中性用橙色。
    static func phaseColor(_ phase: String) -> Color {
        switch phase {
        case "breakout", "uptrend", "range_strong": return Theme.up
        case "breakdown", "downtrend": return Theme.down
        default: return Theme.segment  // topping / bottoming / range / unclear：警示或中性
        }
    }
}

/// 「走势」标签行的短文案映射。
///
/// 后端 `walk_type_label`/`trend_outlook_label` 是给 summary 拼整句用的完整句子
/// （如"当前为上涨趋势（中枢依次抬高）"），直接塞进 Chip 里会太长撑爆一行。这里
/// 按原始枚举码（`walk_type`/`trend_outlook`）单独映射一套「chip 短标签 + 一行
/// 补充说明」，枚举值定义见 `app/services/chan/pivot.py::classify_walk_type` 与
/// `app/services/chan/analyzer.py::_compute_trend_outlook`。
enum WalkTypeFormatting {
    /// 方向复用 K 线涨跌色，盘整用中枢紫，未知状态用中性文字色。
    static func color(_ value: String) -> Color {
        switch value {
        case "up_trend", "reversal_up", "continuation_up", "breakout_up": return Theme.up
        case "down_trend", "reversal_down", "continuation_down", "breakout_down": return Theme.down
        case "consolidation", "range": return Theme.pivotFill
        default: return Theme.textSecondary
        }
    }

    /// 走势类型短标签（用于 Chip）。未知枚举值退回完整句子，避免显示空白。
    static func shortLabel(_ walkType: String, fallback: String?) -> String {
        switch walkType {
        case "up_trend": return L("上涨趋势")
        case "down_trend": return L("下跌趋势")
        case "consolidation": return L("盘整")
        case "none": return L("结构未成形")
        default: return fallback ?? walkType
        }
    }

    /// 走势类型的一行补充说明（对应完整句子里的括号部分）。
    static func detail(_ walkType: String) -> String? {
        switch walkType {
        case "up_trend": return L("中枢依次抬高")
        case "down_trend": return L("中枢依次降低")
        case "consolidation": return L("围绕中枢震荡")
        case "none": return L("单边推进或数据不足")
        default: return nil
        }
    }

    /// 走势展望短标签（用于 Chip）。未知枚举值退回完整句子。
    static func shortOutlookLabel(_ outlook: String, fallback: String?) -> String {
        switch outlook {
        case "reversal_up": return L("可能转折向上")
        case "reversal_down": return L("可能转折向下")
        case "continuation_up": return L("延续上涨")
        case "continuation_down": return L("延续下跌")
        case "breakout_up": return L("向上突破")
        case "breakout_down": return L("向下突破")
        case "range": return L("盘整延续")
        case "unclear": return L("走势不明")
        default: return fallback ?? outlook
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
