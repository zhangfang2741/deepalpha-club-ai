import SwiftUI

/// 全局配色与样式常量，统一深色投研风格。
enum Theme {
    static let accent = Color(hex: 0x3B82F6)      // 主题蓝
    static let background = Color(hex: 0x0B0E14)   // 页面底色
    static let surface = Color(hex: 0x141A24)      // 卡片底色
    static let surfaceAlt = Color(hex: 0x1C2431)   // 次级卡片
    static let border = Color(hex: 0x263041)

    static let textPrimary = Color(hex: 0xE6EDF3)
    static let textSecondary = Color(hex: 0x8B98A9)

    // 涨跌色（全局统一为中国惯例：红涨绿跌）。
    // 语义按「涨/跌」而非固定红绿，全 App 引用 Theme.up/down，翻转只需改这两行：
    // K 线、MACD 柱、趋势/偏向配色都会随之一致翻转。
    static let up = Color(hex: 0xF6465D)   // 涨=红
    static let down = Color(hex: 0x2EBD85) // 跌=绿

    // 缠论结构叠加色
    static let stroke = Color(hex: 0x60A5FA)       // 笔
    static let segment = Color(hex: 0xF59E0B)      // 线段
    static let pivotFill = Color(hex: 0x8B5CF6)    // 中枢
    static let topFractal = Color(hex: 0xEF4444)   // 顶分型
    static let bottomFractal = Color(hex: 0x22C55E)// 底分型
    static let divergence = Color(hex: 0xEC4899)   // 背驰标注（与线段橙区分）

    // MARK: - 内容容器边距

    /// 滚动内容容器的水平内边距。
    ///
    /// 卡片自带 16pt 内边距，容器原本再给 14pt，文字离屏幕边就有 30pt——一眼看去
    /// 两侧空荡荡像没铺满。收到 8pt 后卡片接近贴边，文字距边 24pt 仍然够透气，
    /// 图表也多出 12pt 可用宽度。
    static let contentHInset: CGFloat = 8
    /// 滚动内容容器的垂直内边距（首尾留白，与卡片间距一致）。
    static let contentVInset: CGFloat = 14

    /// 中枢阶段 → 标签配色：形成/震荡（还没怎样）用中性灰，离开段（正在发生）用
    /// 橙，回抽确认（已确认）用主题蓝，背驰转折（趋势信号）用紫。自选列表标签和
    /// 详情页「走到哪一步」徽标共用同一套映射，同一只票同一阶段在两处颜色一致。
    static func pivotPhaseColor(_ phase: String?) -> Color {
        switch phase {
        case "leaving": return Theme.segment
        case "retrace_confirmed": return Theme.accent
        case "divergence_turn": return Theme.pivotFill
        default: return Theme.textSecondary  // pivot_forming / pivot_oscillating / nil
        }
    }
}

extension Color {
    /// 用 0xRRGGBB 十六进制初始化颜色。
    init(hex: UInt32, alpha: Double = 1.0) {
        let r = Double((hex >> 16) & 0xFF) / 255.0
        let g = Double((hex >> 8) & 0xFF) / 255.0
        let b = Double(hex & 0xFF) / 255.0
        self.init(.sRGB, red: r, green: g, blue: b, opacity: alpha)
    }
}
