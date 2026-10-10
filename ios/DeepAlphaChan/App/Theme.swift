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
    /// 均线三条，按周期从短到长依次取色。避开红 / 绿（只给买卖点）和笔 / 中枢 / 背驰已用的蓝 / 紫 / 粉。
    static let maColors: [Color] = [Color(hex: 0xE5E7EB), Color(hex: 0x22D3EE), Color(hex: 0xFACC15)]
    /// 指数均线两条（12 / 26）；布林带三条线同色（石板灰），带内浅色填充。同样避开红 / 绿。
    static let emaColors: [Color] = [Color(hex: 0xFB923C), Color(hex: 0xF0ABFC)]
    static let bollLine = Color(hex: 0x94A3B8)
    /// 威科夫（交易区间 + 事件标记）：浅棕，避开红 / 绿（只给买卖点）与笔 / 中枢 / 背驰 / 均线已用的颜色。
    static let wyckoff = Color(hex: 0xD4A373)
    /// 基本面动向雷达：预期上调 / 质地改善（避开红绿——红绿只给已成立的买卖点）
    static let trendEstimates = Color(hex: 0x3B82F6)
    static let trendQuality = Color(hex: 0xA855F7)

    // MARK: - 内容容器边距

    /// 滚动内容容器的水平内边距。
    ///
    /// 卡片自带 16pt 内边距，容器原本再给 14pt，文字离屏幕边就有 30pt——一眼看去
    /// 两侧空荡荡像没铺满。收到 8pt 后卡片接近贴边，文字距边 24pt 仍然够透气，
    /// 图表也多出 12pt 可用宽度。
    static let contentHInset: CGFloat = 8
    /// 滚动内容容器的垂直内边距（首尾留白，与卡片间距一致）。
    static let contentVInset: CGFloat = 14

    /// 中枢阶段的配色：自选列表的状态标签、详情页的阶段标题、判定图的当前节点共用，三处必须一致。
    ///
    /// 2026-10-05 起一律用中性主题蓝，**不再按多空倾向用红 / 绿**：红 / 绿在本 App 只表示已成立的买卖点。
    /// 以前阶段标题也按偏多 / 偏空着红绿，同一页里「红色一买 + 绿色阶段标题 + 绿色待确认三卖」会被读成又买又卖
    /// （如 APP 2026-09-01：一买已成立，阶段「反弹未升回中枢」只是结构描述）。
    /// 方向改用箭头表达（`phaseArrow`），参数保留以便三处调用方不用改。
    static func phaseColor(phase: String?, direction: String?) -> Color {
        Theme.accent
    }

    /// 阶段方向箭头的 SF Symbol 名：离开中枢的方向（价格向上 / 向下），不带偏多偏空含义。
    /// 没有方向（中枢形成 / 震荡）返回 nil。
    static func phaseArrow(direction: String?) -> String? {
        switch direction {
        case "up": return "arrow.up"
        case "down": return "arrow.down"
        default: return nil
        }
    }

    /// 「当前」标记的颜色（判定图节点角标、详情卡片标题旁）：用中性主题蓝，
    /// 不用红 / 绿——那两色在本 App 专指买 / 卖，当前节点偏多时绿角标会误读成卖。
    static let currentBadge = Theme.accent
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
